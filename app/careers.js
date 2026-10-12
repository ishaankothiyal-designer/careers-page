'use strict';
const $ = (selector) => document.querySelector(selector);
const filterForm = $('#job-filters');
const jobList = $('#job-list');
const dialog = $('#job-dialog');
const applicationForm = $('#application-form');
let selectedJob = null;
let dialogTrigger = null;
let listRequest = null;
let detailRequest = null;
let filterTimer;
let submitting = false;
let populatedFilters = false;
let allJobs = [];
let matchingJobs = [];
let visibleLimit = 12;
let requestCounter = 0;
async function api(url, options = {}) {
  const response = await fetch(url, options);
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unexpected response. Please try again.'); }
  if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}
function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function replaceOptions(selector, values, firstLabel) {
  const select = $(selector), previous = select.value;
  select.replaceChildren();
  const first = make('option', '', firstLabel); first.value = ''; select.append(first);
  [...new Set(values.filter(Boolean))].sort().forEach(value => {
    const option = make('option', '', value); option.value = value; select.append(option);
  });
  select.value = [...select.options].some(option => option.value === previous) ? previous : '';
}
function updateFacets() {
  const country = $('#job-country').value;
  const countryJobs = allJobs.filter(job => !country || job.country === country);
  const label = country === 'India' ? 'State / union territory' : country === 'Australia' ? 'State / territory' : ['UAE','United Arab Emirates'].includes(country) ? 'Emirate' : 'State / region';
  $('#job-state-label').textContent = label;
  const allRegionLabel = country === 'India' ? 'All states / union territories' : country === 'Australia' ? 'All states / territories' : ['UAE','United Arab Emirates'].includes(country) ? 'All emirates' : 'All states / regions';
  replaceOptions('#job-state', countryJobs.map(job => job.state), allRegionLabel);
  const state = $('#job-state').value;
  replaceOptions('#job-location', countryJobs.filter(job => !state || job.state === state).map(job => job.location), 'All cities / locations');
  const context = [country,state,$('#job-location').value].filter(Boolean);
  $('#filter-context').textContent = context.length ? 'Exploring '+context.join(' · ')+'.' : 'Explore all countries, regions, and locations.';
}
function populateFilters(jobs) {
  allJobs = jobs;
  replaceOptions('#job-country', jobs.map(job => job.country), 'All countries');
  replaceOptions('#job-team', jobs.map(job => job.team), 'All teams');
  replaceOptions('#job-mode', jobs.map(job => job.work_mode), 'All models');
  updateFacets();
}
function renderJobs(jobs) {
  jobList.replaceChildren();
  jobs.slice(0,visibleLimit).forEach(job => {
    const row = make('button','job-row'); row.type = 'button'; row.dataset.jobId = job.id;
    const titleColumn = make('span');
    titleColumn.append(make('strong','',job.title),make('span','job-team',job.team));
    if (job.first_90_days) titleColumn.append(make('span','job-outcome','First 90 days: '+job.first_90_days));
    const meta = make('span','job-meta',[job.location,job.state,job.country,job.work_mode,job.employment_type].filter(Boolean).join(' · '));
    row.append(titleColumn,meta,make('span','job-action','View role →'));
    row.addEventListener('click',() => openJob(job.id,row));
    jobList.append(row);
  });
  $('#job-empty').hidden = jobs.length !== 0;
  $('#job-status').textContent = Math.min(visibleLimit,jobs.length)+' of '+jobs.length+' matching '+(jobs.length===1?'role':'roles');
  $('#load-more-wrap').hidden = visibleLimit >= jobs.length;
}
async function loadJobs() {
  listRequest?.abort(); listRequest = new AbortController();
  const current = ++requestCounter;
  $('#job-error').hidden = true; $('#job-empty').hidden = true; $('#load-more-wrap').hidden = true;
  visibleLimit = 12;
  $('#job-status').textContent = 'Loading open roles…';
  jobList.setAttribute('aria-busy','true');
  const params = new URLSearchParams(new FormData(filterForm));
  try {
    let data = await api('/api/jobs?'+(populatedFilters ? params : ''),{signal:listRequest.signal});
    if (current !== requestCounter) return;
    if (!Array.isArray(data.jobs)) throw new Error('The roles response was incomplete. Please try again.');
    if (!populatedFilters) {
      populateFilters(data.jobs);populatedFilters=true;
      if([...params.values()].some(Boolean)){
        data=await api('/api/jobs?'+params,{signal:listRequest.signal});
        if(current!==requestCounter)return;
      }
    }
    matchingJobs = data.jobs; renderJobs(matchingJobs);
  } catch(error) {
    if(error.name==='AbortError'||current!==requestCounter)return;
    jobList.replaceChildren();$('#job-status').textContent='Roles unavailable';
    $('#job-error-message').textContent=error.message;$('#job-error').hidden=false;
  } finally {if(current===requestCounter)jobList.setAttribute('aria-busy','false');}
}
filterForm.addEventListener('submit',event=>{event.preventDefault();clearTimeout(filterTimer);loadJobs();});
$('#job-search').addEventListener('input',()=>{clearTimeout(filterTimer);filterTimer=setTimeout(loadJobs,220);});
filterForm.querySelectorAll('select').forEach(select=>select.addEventListener('change',()=>{
  if(select.id==='job-country'){$('#job-state').value='';$('#job-location').value='';}
  if(select.id==='job-state')$('#job-location').value='';
  updateFacets();clearTimeout(filterTimer);loadJobs();
}));
$('#load-more-jobs').addEventListener('click',()=>{const firstNew=visibleLimit;visibleLimit+=12;renderJobs(matchingJobs);jobList.children[firstNew]?.focus();});
$('#retry-jobs').addEventListener('click',loadJobs);
$('#clear-filters').addEventListener('click',()=>{filterForm.reset();updateFacets();loadJobs();$('#job-search').focus();});
function resetApplication() {
  applicationForm.reset();applicationForm.hidden=false;
  $('#application-success').hidden=true;$('#application-error').hidden=true;
  $('#submit-application').disabled=false;$('#submit-application').textContent='Send application';
  submitting=false;
}
async function openJob(id,trigger) {
  if(submitting)return;
  detailRequest?.abort();detailRequest=new AbortController();
  selectedJob=null;dialogTrigger=trigger||$('#job-search');
  $('#role-content').hidden=true;$('#dialog-error').hidden=true;$('#dialog-loading').hidden=false;
  $('#dialog-title').textContent='Role details';resetApplication();
  if(!dialog.open)dialog.showModal();
  $('#close-dialog').focus();
  try {
    const {job}=await api('/api/jobs/'+encodeURIComponent(id),{signal:detailRequest.signal});
    if(!dialog.open)return;
    if(!job)throw new Error('This opportunity is not available.');
    selectedJob=job;
    $('#dialog-title').textContent=job.title;
    $('#dialog-meta').textContent=[job.team,job.location,job.state,job.country,job.work_mode,job.employment_type].filter(Boolean).join(' · ');
    [['description','#role-description'],['responsibilities','#role-responsibilities'],['requirements','#role-requirements'],['first_90_days','#role-first-90']].forEach(([key,target])=>{$(target).textContent=job[key]||'Details to be supplied by the role owner.';});
    $('#role-content').hidden=false;
  }catch(error){if(error.name!=='AbortError'){$('#dialog-error').textContent=error.message;$('#dialog-error').hidden=false;}}
  finally{$('#dialog-loading').hidden=true;}
}
function closeDialog(){if(!submitting)dialog.close();}
$('#close-dialog').addEventListener('click',closeDialog);
$('#success-close').addEventListener('click',closeDialog);
dialog.addEventListener('cancel',event=>{if(submitting)event.preventDefault();});
dialog.addEventListener('close',()=>{detailRequest?.abort();dialogTrigger?.focus();selectedJob=null;});
dialog.addEventListener('click',event=>{if(event.target===dialog){const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)closeDialog();}});
applicationForm.addEventListener('submit',async event=>{
  event.preventDefault();if(submitting||!selectedJob||!applicationForm.reportValidity())return;
  const payload=Object.fromEntries(new FormData(applicationForm));
  Object.keys(payload).forEach(key=>payload[key]=payload[key].trim());
  if(!payload.name||!payload.statement){$('#application-error').textContent='Please enter your name and tell us about something you built.';$('#application-error').hidden=false;return;}
  if(payload.portfolio_url){try{const url=new URL(payload.portfolio_url);if(!['http:','https:'].includes(url.protocol))throw new Error();}catch{$('#application-error').textContent='Your work link must start with http:// or https://.';$('#application-error').hidden=false;$('#applicant-portfolio').focus();return;}}
  submitting=true;$('#submit-application').disabled=true;$('#submit-application').textContent='Sending application…';$('#close-dialog').disabled=true;$('#application-error').hidden=true;
  try {
    const result=await api('/api/jobs/'+encodeURIComponent(selectedJob.id)+'/applications',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    applicationForm.hidden=true;$('#application-reference').textContent=result.reference||result.id;
    $('#success-message').textContent='Your application for '+(result.job_title||selectedJob.title)+' has been received.';
    $('#application-success').hidden=false;$('#application-success').focus();
  }catch(error){$('#application-error').textContent=error.message;$('#application-error').hidden=false;}
  finally{submitting=false;$('#submit-application').disabled=false;$('#submit-application').textContent='Send application';$('#close-dialog').disabled=false;}
});
document.querySelectorAll('[data-story-filter]').forEach(button=>button.addEventListener('click',()=>{
  const filter=button.dataset.storyFilter;let count=0;
  document.querySelectorAll('[data-story-filter]').forEach(item=>{const active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-pressed',String(active));});
  document.querySelectorAll('.story').forEach(story=>{story.hidden=filter!=='all'&&story.dataset.team!==filter;story.classList.remove('is-filtered-in');if(!story.hidden){count++;requestAnimationFrame(()=>story.classList.add('is-filtered-in'));}});
  $('#story-status').textContent='Showing '+count+' builder '+(count===1?'story.':'stories.');
}));
const motionPreference=window.matchMedia('(prefers-reduced-motion: reduce)');
let observer;
function setupReveals(){
  observer?.disconnect();
  document.querySelectorAll('[data-reveal]').forEach(section=>section.classList.remove('reveal-pending'));
  if(motionPreference.matches||!('IntersectionObserver'in window))return;
  observer=new IntersectionObserver(entries=>entries.forEach(entry=>{if(entry.isIntersecting){entry.target.classList.remove('reveal-pending');observer.unobserve(entry.target);}}),{threshold:.06});
  document.querySelectorAll('[data-reveal]').forEach(section=>{if(section.getBoundingClientRect().top>window.innerHeight){section.classList.add('reveal-pending');observer.observe(section);}});
}
setupReveals();
motionPreference.addEventListener('change',()=>{if(motionPreference.matches){observer?.disconnect();document.querySelectorAll('.reveal-pending').forEach(section=>section.classList.remove('reveal-pending'));document.getAnimations().forEach(animation=>animation.cancel());}});
let progressTicking=false;
window.addEventListener('scroll',()=>{if(progressTicking)return;progressTicking=true;requestAnimationFrame(()=>{const available=document.documentElement.scrollHeight-window.innerHeight;$('.reading-progress span').style.transform='scaleX('+(available?Math.min(1,window.scrollY/available):0)+')';progressTicking=false;});},{passive:true});
loadJobs();
const deepLinkedJob=new URLSearchParams(location.search).get('job');
if(deepLinkedJob)openJob(deepLinkedJob,$('#job-search'));
