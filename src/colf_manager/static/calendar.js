let calendar;
function csrfToken(){return document.querySelector('meta[name="csrf-token"]').content;}
document.addEventListener('DOMContentLoaded',()=>{
  calendar=new FullCalendar.Calendar(document.getElementById('calendar'),{
    initialView:'dayGridMonth', locale:'it', firstDay:1, editable:true, selectable:true, height:'auto',
    customButtons:{previousMonth:{text:'← Mese precedente',click:()=>calendar.prev()},nextMonth:{text:'Mese successivo →',click:()=>calendar.next()}},
    headerToolbar:{left:'previousMonth,nextMonth today',center:'title',right:''}, buttonText:{today:'Oggi'},
    events:(info,ok,fail)=>fetch('/api/events?worker_id='+document.getElementById('workerFilter').value).then(r=>r.json()).then(ok).catch(fail),
    dateClick:i=>openModal(i.dateStr),
    eventDrop:async i=>{if(!i.event.id.startsWith('work-'))return i.revert();const body={work_date:i.event.startStr.slice(0,10),start_time:i.event.startStr.slice(11,16),end_time:i.event.endStr?.slice(11,16)};const r=await fetch('/api/work/'+i.event.id.split('-')[1],{method:'PATCH',headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken()},body:JSON.stringify(body)});if(!r.ok)i.revert();}
  });
  calendar.render();
  document.getElementById('workerFilter').onchange=()=>calendar.refetchEvents();
  document.getElementById('workForm').onsubmit=async e=>{e.preventDefault();const body=Object.fromEntries(new FormData(e.target));const r=await fetch('/api/work',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':csrfToken()},body:JSON.stringify(body)});if(r.ok){workDialog.close();calendar.refetchEvents()}else{const data=await r.json().catch(()=>({}));alert(data.error||'Controlla i dati inseriti.');}};
});
function localDateString(d){const y=d.getFullYear();const m=String(d.getMonth()+1).padStart(2,'0');const day=String(d.getDate()).padStart(2,'0');return `${y}-${m}-${day}`;}
function openModal(day){const d=document.getElementById('workDialog');const chosen=day||localDateString(calendar.getDate());d.querySelector('[name=work_date]').value=chosen;d.showModal();}
