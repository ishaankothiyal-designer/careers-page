const securityHeaders = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: https:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
  'Cache-Control': 'no-store'
};
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if(url.pathname.startsWith('/api/')) return handleApi(request,env);
    if(!['GET','HEAD'].includes(request.method)) return new Response('Method not allowed',{status:405});
    const path = ({'/':'/index.html','/jobs':'/jobs.html','/jobs/':'/jobs.html','/admin':'/admin.html','/admin/':'/admin.html'})[url.pathname] || url.pathname;
    const asset = ASSETS[path];
    if(!asset) return new Response('Page not found',{status:404,headers:securityHeaders});
    const body = request.method === 'HEAD' ? null : Uint8Array.from(atob(asset.body), c => c.charCodeAt(0));
    return new Response(body,{headers:{...securityHeaders,'Content-Type':asset.type+(asset.type.startsWith('text/')||asset.type==='application/javascript'?'; charset=utf-8':'')}});
  }
};
