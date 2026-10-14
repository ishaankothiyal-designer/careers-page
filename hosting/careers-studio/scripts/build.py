from pathlib import Path
import base64, json, mimetypes, shutil
root=Path(__file__).resolve().parents[1]
dist=root/'dist'
if dist.exists(): shutil.rmtree(dist)
(dist/'server').mkdir(parents=True); (dist/'.openai').mkdir()
assets={}
for path in sorted((root/'app').rglob('*')):
 if path.is_file():
  name='/'+path.relative_to(root/'app').as_posix()
  assets[name]={'type':mimetypes.guess_type(path.name)[0] or 'application/octet-stream','body':base64.b64encode(path.read_bytes()).decode()}
seed=(root/'worker/seed.mjs').read_text().replace('export default ','const seedJobs = ',1)
api=(root/'worker/api.mjs').read_text().replace("import seedJobs from './seed.mjs';",'').replace('export async function handleApi','async function handleApi')
entry=(root/'worker/index.mjs').read_text()
(dist/'server/index.js').write_text(seed+'\n'+api+'\nconst ASSETS = '+json.dumps(assets)+';\n'+entry)
shutil.copy2(root/'.openai/hosting.json',dist/'.openai/hosting.json')
if (root/'drizzle').exists():
 shutil.copytree(root/'drizzle',dist/'drizzle')
print('Built one self-contained Worker with frontend, fonts, seed catalogue, and API.')
