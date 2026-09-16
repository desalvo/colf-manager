let calendar;
const workDialog = document.getElementById('workDialog');
const workForm = document.getElementById('workForm');
const deleteWorkButton = document.getElementById('deleteWorkButton');
const entryKind = document.getElementById('entryKind');
const workOnlyFields = document.getElementById('workOnlyFields');
const permitOnlyFields = document.getElementById('permitOnlyFields');
const sicknessOnlyFields = document.getElementById('sicknessOnlyFields');
const vacationOnlyFields = document.getElementById('vacationOnlyFields');
const endDateField = document.getElementById('endDateField');
const paidEntry = document.getElementById('paidEntry');
const favorableTreatmentField = document.getElementById('favorableTreatmentField');
const paidBeyondLegalLimit = document.getElementById('paidBeyondLegalLimit');
const overtimeRateField = document.getElementById('overtimeRateField');
const timeFields = document.getElementById('timeFields');
const permitCategory = document.getElementById('permitCategory');

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]').content;
}

function localDateString(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function timeString(date) {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function addMinutes(date, minutes) {
  return new Date(date.getTime() + Number(minutes) * 60000);
}


function setVisible(element, visible) {
  if (!element) return;
  element.hidden = !visible;
  element.classList.toggle('hidden', !visible);
}

function syncEntryKind() {
  const kind = entryKind.value;
  const isWork = ['ordinary', 'overtime'].includes(kind);
  const isPermit = kind === 'permit';
  const isSickness = kind === 'sickness';
  const isVacation = kind === 'vacation';
  const usesTime = isWork || isPermit;

  setVisible(workOnlyFields, isWork);
  setVisible(permitOnlyFields, isPermit);
  setVisible(sicknessOnlyFields, isSickness);
  setVisible(vacationOnlyFields, isVacation);
  setVisible(endDateField, !isWork);
  setVisible(timeFields, usesTime);
  setVisible(overtimeRateField, kind === 'overtime');

  workForm.querySelector('[name=location_id]').required = isWork;
  workForm.querySelector('[name=end_date]').required = !isWork;
  workForm.querySelector('[name=start_time]').required = usesTime;
  workForm.querySelector('[name=end_time]').required = usesTime;
  paidEntry.disabled = false;
  setVisible(document.getElementById('paidEntryField'), !isVacation);
  setVisible(favorableTreatmentField, isPermit || isSickness);

  if (!isWork) {
    const firstDate = workForm.querySelector('[name=work_date]').value;
    if (!workForm.querySelector('[name=end_date]').value) {
      workForm.querySelector('[name=end_date]').value = firstDate;
    }
    if (isPermit && permitCategory && !permitCategory.value) permitCategory.value = 'medical';
  }
}

function resetWorkForm() {
  workForm.reset();
  workForm.querySelector('[name=record_id]').value = '';
  entryKind.value = 'ordinary';
  workForm.querySelector('[name=start_time]').value = '09:00';
  workForm.querySelector('[name=end_time]').value = '13:00';
  workForm.querySelector('[name=break_minutes]').value = '0';
  paidEntry.checked = true;
  paidEntry.disabled = false;
  workForm.querySelector('[name=rate_override]').value = '';
  paidBeyondLegalLimit.checked = false;
  document.getElementById('workDialogTitle').textContent = 'Nuova registrazione';
  deleteWorkButton.classList.add('hidden');
  syncEntryKind();
}

function openEntryModal(day, startTime, kind = 'ordinary') {
  resetWorkForm();
  entryKind.value = kind;
  const chosen = day || localDateString(calendar.getDate());
  workForm.querySelector('[name=work_date]').value = chosen;
  workForm.querySelector('[name=end_date]').value = chosen;
  if (startTime) {
    workForm.querySelector('[name=start_time]').value = startTime;
    const [hour, minute] = startTime.split(':').map(Number);
    const end = new Date(2000, 0, 1, hour, minute + 60);
    workForm.querySelector('[name=end_time]').value = timeString(end);
  }
  syncEntryKind();
  workDialog.showModal();
}
window.openEntryModal = openEntryModal;

function openEditModal(event) {
  resetWorkForm();
  const props = event.extendedProps;
  if (props.type === 'work') {
    entryKind.value = props.entry_kind || 'ordinary';
    workForm.querySelector('[name=record_id]').value = event.id.replace('work-', '');
    workForm.querySelector('[name=worker_id]').value = props.worker_id;
    workForm.querySelector('[name=work_date]').value = event.startStr.slice(0, 10);
    workForm.querySelector('[name=start_time]').value = event.startStr.slice(11, 16);
    workForm.querySelector('[name=end_time]').value = event.endStr.slice(11, 16);
    workForm.querySelector('[name=location_id]').value = props.location_id || '';
    workForm.querySelector('[name=break_minutes]').value = props.break_minutes || 0;
    paidEntry.checked = props.paid !== false;
    workForm.querySelector('[name=rate_override]').value = props.rate_override || '';
    workForm.querySelector('[name=notes]').value = props.notes || '';
    document.getElementById('workDialogTitle').textContent = props.entry_kind === 'overtime' ? 'Modifica ore straordinarie' : 'Modifica ore ordinarie';
  } else if (props.type === 'absence') {
    entryKind.value = props.entry_kind;
    workForm.querySelector('[name=record_id]').value = props.absence_id;
    workForm.querySelector('[name=worker_id]').value = props.worker_id;
    workForm.querySelector('[name=work_date]').value = props.start_date;
    workForm.querySelector('[name=end_date]').value = props.end_date;
    workForm.querySelector('[name=start_time]').value = props.start_time;
    workForm.querySelector('[name=end_time]').value = props.end_time;
    paidEntry.checked = Boolean(props.paid);
    paidBeyondLegalLimit.checked = ['permit', 'sickness'].includes(props.entry_kind) && Boolean(props.paid_beyond_legal_limit);
    workForm.querySelector('[name=oncological]').checked = Boolean(props.oncological);
    if (permitCategory) permitCategory.value = props.permit_category || (props.paid ? 'medical' : 'other');
    workForm.querySelector('[name=notes]').value = props.notes || '';
    document.getElementById('workDialogTitle').textContent = props.entry_kind === 'vacation' ? 'Modifica ferie' : props.entry_kind === 'sickness' ? 'Modifica malattia' : 'Modifica permesso';
  } else {
    return;
  }
  syncEntryKind();
  deleteWorkButton.classList.remove('hidden');
  workDialog.showModal();
}

async function openAbsenceById(absenceId) {
  const response = await fetch(`/api/absence/${absenceId}`);
  if (!response.ok) {
    alert('Impossibile caricare la registrazione.');
    return;
  }
  const data = await response.json();
  resetWorkForm();
  entryKind.value = data.kind;
  workForm.querySelector('[name=record_id]').value = data.id;
  workForm.querySelector('[name=worker_id]').value = data.worker_id;
  workForm.querySelector('[name=work_date]').value = data.start_date;
  workForm.querySelector('[name=end_date]').value = data.end_date;
  workForm.querySelector('[name=start_time]').value = data.start_time;
  workForm.querySelector('[name=end_time]').value = data.end_time;
  paidEntry.checked = Boolean(data.paid);
  paidBeyondLegalLimit.checked = ['permit', 'sickness'].includes(data.kind) && Boolean(data.paid_beyond_legal_limit);
  workForm.querySelector('[name=oncological]').checked = Boolean(data.oncological);
  if (permitCategory) permitCategory.value = data.permit_category || (data.paid ? 'medical' : 'other');
  workForm.querySelector('[name=notes]').value = data.notes || '';
  document.getElementById('workDialogTitle').textContent = data.kind === 'vacation' ? 'Modifica ferie' : data.kind === 'sickness' ? 'Modifica malattia' : 'Modifica permesso';
  syncEntryKind();
  deleteWorkButton.classList.remove('hidden');
  workDialog.showModal();
}

async function saveWork(payload, entryId) {
  const url = entryId ? `/api/work/${entryId}` : '/api/work';
  const method = entryId ? 'PATCH' : 'POST';
  const response = await fetch(url, {
    method,
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Controlla i dati inseriti.');
  return data;
}

async function saveAbsence(payload, absenceId) {
  const url = absenceId ? `/api/absence/${absenceId}` : '/api/absence';
  const method = absenceId ? 'PATCH' : 'POST';
  const response = await fetch(url, {
    method,
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Controlla i dati inseriti.');
  return data;
}

async function deleteCurrentRecord() {
  const recordId = workForm.querySelector('[name=record_id]').value;
  if (!recordId) return;
  const kind = entryKind.value;
  const isWork = ['ordinary', 'overtime'].includes(kind);
  const label = isWork ? 'questa registrazione di ore' : kind === 'vacation' ? 'queste ferie' : kind === 'sickness' ? 'questa registrazione di malattia' : 'questo permesso';
  if (!confirm(`Eliminare definitivamente ${label}?`)) return;
  const response = await fetch(isWork ? `/api/work/${recordId}` : `/api/absence/${recordId}`, {
    method: 'DELETE',
    headers: {'X-CSRFToken': csrfToken()},
  });
  if (!response.ok) {
    alert('Impossibile eliminare la registrazione.');
    return;
  }
  workDialog.close();
  calendar.refetchEvents();
}

function initExternalPatterns() {
  const container = document.getElementById('recentPatterns');
  if (!container || !window.FullCalendar?.Draggable) return;
  new FullCalendar.Draggable(container, {
    itemSelector: '.quick-pattern',
    eventData: (el) => {
      const color = getComputedStyle(el).getPropertyValue('--event-color').trim();
      return {
        title: ['ordinary', 'overtime'].includes(el.dataset.kind) ? el.querySelector('.pattern-kind')?.textContent || 'Ore' : el.querySelector('.pattern-kind')?.textContent || 'Registrazione',
        duration: {minutes: Number(el.dataset.duration || 60)},
        backgroundColor: color,
        borderColor: color,
        textColor: '#ffffff',
        extendedProps: {
          quickPattern: true,
          entry_kind: el.dataset.kind || 'ordinary',
          worker_id: el.dataset.workerId,
          location_id: el.dataset.locationId,
          break_minutes: el.dataset.break,
          duration_minutes: el.dataset.duration,
          start_time: el.dataset.start,
          end_time: el.dataset.end,
          paid: el.dataset.paid === '1',
          paid_hours: el.dataset.paidHours || '',
          rate_override: el.dataset.rateOverride || '',
          event_color: color,
        },
      };
    },
  });
}

document.addEventListener('DOMContentLoaded', () => {
  entryKind.addEventListener('change', () => {
    if (!workForm.querySelector('[name=record_id]').value) paidEntry.checked = true;
    syncEntryKind();
  });
  workForm.querySelector('[name=work_date]').addEventListener('change', () => {
    if (!['ordinary', 'overtime'].includes(entryKind.value) && !workForm.querySelector('[name=end_date]').value) {
      workForm.querySelector('[name=end_date]').value = workForm.querySelector('[name=work_date]').value;
    }
  });

  calendar = new FullCalendar.Calendar(document.getElementById('calendar'), {
    initialView: window.matchMedia('(max-width: 850px)').matches ? 'dayGridMonth' : 'timeGridWeek',
    locale: 'it',
    firstDay: 1,
    editable: true,
    selectable: true,
    droppable: true,
    nowIndicator: true,
    allDaySlot: false,
    slotDuration: '00:30:00',
    slotMinTime: '06:00:00',
    slotMaxTime: '23:00:00',
    height: 'auto',
    expandRows: true,
    eventMinHeight: 28,
    eventTimeFormat: {hour: '2-digit', minute: '2-digit', hour12: false},
    customButtons: {
      previousPeriod: {text: '←', hint: 'Periodo precedente', click: () => calendar.prev()},
      nextPeriod: {text: '→', hint: 'Periodo successivo', click: () => calendar.next()},
    },
    headerToolbar: {left: 'previousPeriod,nextPeriod today', center: 'title', right: 'dayGridMonth,timeGridWeek,timeGridDay'},
    buttonText: {today: 'Oggi', month: 'Mese', week: 'Settimana', day: 'Giorno'},
    events: (info, ok, fail) => fetch(`/api/events?worker_id=${document.getElementById('workerFilter').value}`)
      .then((response) => response.json()).then(ok).catch(fail),
    dateClick: (info) => openEntryModal(info.dateStr.slice(0, 10), info.allDay ? null : timeString(info.date)),
    eventClick: (info) => openEditModal(info.event),
    eventDrop: async (info) => {
      if (info.event.extendedProps.type !== 'work') return info.revert();
      try {
        await saveWork({work_date: info.event.startStr.slice(0, 10), start_time: info.event.startStr.slice(11, 16), end_time: info.event.endStr?.slice(11, 16)}, info.event.id.replace('work-', ''));
      } catch (error) { alert(error.message); info.revert(); }
    },
    eventResize: async (info) => {
      if (info.event.extendedProps.type !== 'work') return info.revert();
      try {
        await saveWork({work_date: info.event.startStr.slice(0, 10), start_time: info.event.startStr.slice(11, 16), end_time: info.event.endStr?.slice(11, 16)}, info.event.id.replace('work-', ''));
      } catch (error) { alert(error.message); info.revert(); }
    },
    eventReceive: async (info) => {
      const props = info.event.extendedProps;
      if (!props.quickPattern) return;
      try {
        const targetDay = localDateString(info.event.start);
        const kind = props.entry_kind || 'work';
        if (['ordinary', 'overtime'].includes(kind)) {
          await saveWork({
            worker_id: props.worker_id,
            location_id: props.location_id,
            work_date: targetDay,
            start_time: props.start_time,
            end_time: props.end_time,
            break_minutes: props.break_minutes || 0,
            entry_kind: kind,
            paid: Boolean(props.paid),
            rate_override: props.rate_override || '',
          });
        } else {
          await saveAbsence({
            worker_id: props.worker_id,
            kind,
            start_date: targetDay,
            end_date: targetDay,
            start_time: props.start_time,
            end_time: props.end_time,
            paid: Boolean(props.paid),
            paid_hours: props.paid_hours || '',
          });
        }
        info.event.remove();
        calendar.refetchEvents();
      } catch (error) { alert(error.message); info.event.remove(); }
    },
    datesSet: (info) => {
      const calendarEl = document.getElementById('calendar');
      calendarEl.classList.toggle('timegrid-active', info.view.type.startsWith('timeGrid'));
      window.requestAnimationFrame(() => calendar.updateSize());
    },
    windowResize: () => {
      window.requestAnimationFrame(() => calendar.updateSize());
    },
    eventContent: (arg) => {
      const props = arg.event.extendedProps;
      const wrap = document.createElement('div');
      const isMonth = arg.view.type === 'dayGridMonth';
      wrap.className = isMonth ? 'calendar-event-content month-compact' : 'calendar-event-content';
      const start = arg.event.start ? timeString(arg.event.start) : '';
      const end = arg.event.end ? timeString(arg.event.end) : '';
      const timeRange = ['vacation','sickness'].includes(props.entry_kind) ? `${props.vacation_days || props.sickness_days || ''} giorni` : (end ? `${start}–${end}` : start);
      if (isMonth) {
        wrap.innerHTML = `<b class="event-time">${timeRange}</b>`;
      } else if (props.type === 'work') {
        wrap.innerHTML = `<b class="event-time">${timeRange}</b><span>${props.kind_label || 'Ore ordinarie'}${props.paid === false ? ' · non retribuite' : ''}</span><small>${props.worker}</small><small>${props.employer}</small><small>${props.location}</small>`;
      } else {
        wrap.innerHTML = `<b class="event-time">${timeRange}</b><span>${props.kind_label}</span><small>${props.worker}</small><small>${props.employer}</small>`;
      }
      return {domNodes: [wrap]};
    },
    eventDidMount: (info) => {
      const props = info.event.extendedProps;
      const eventColor = info.event.backgroundColor || props.event_color || info.event.borderColor;
      if (eventColor) {
        info.el.style.setProperty('--fc-event-bg-color', eventColor);
        info.el.style.setProperty('--fc-event-border-color', eventColor);
        info.el.style.backgroundColor = eventColor;
        info.el.style.borderColor = eventColor;
        const main = info.el.querySelector('.fc-event-main');
        if (main) main.style.backgroundColor = eventColor;
      }
      const start = info.event.start ? timeString(info.event.start) : '';
      const end = info.event.end ? timeString(info.event.end) : '';
      const details = props.type === 'work' ? [
        `${start}${end ? `–${end}` : ''}`,
        `Lavoratore: ${props.worker || '—'}`,
        `Datore: ${props.employer || '—'}`,
        `Luogo: ${props.location || '—'}`,
      ] : [
        props.entry_kind === 'vacation' ? `Ferie: ${props.vacation_days || ''} giorni` : props.entry_kind === 'sickness' ? `Malattia: ${props.sickness_days || ''} giorni` : `${props.kind_label}: ${start}${end ? `–${end}` : ''}`,
        `Lavoratore: ${props.worker || '—'}`,
        `Datore: ${props.employer || '—'}`,
        `Periodo: ${props.start_date} → ${props.end_date} (estremi inclusi)`,
      ];
      info.el.title = details.join('\n');
      info.el.setAttribute('aria-label', details.join('. '));
      info.el.tabIndex = 0;
    },
  });
  calendar.render();
  window.requestAnimationFrame(() => calendar.updateSize());
  window.addEventListener('orientationchange', () => {
    window.setTimeout(() => calendar.updateSize(), 120);
  });
  initExternalPatterns();
  document.getElementById('workerFilter').addEventListener('change', () => calendar.refetchEvents());

  document.querySelectorAll('.edit-absence-shortcut').forEach((button) => button.addEventListener('click', () => {
    openAbsenceById(button.dataset.absenceId);
  }));

  workForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = Object.fromEntries(new FormData(workForm));
    const recordId = formData.record_id;
    const kind = formData.entry_kind;
    delete formData.record_id;
    delete formData.entry_kind;
    try {
      if (['ordinary', 'overtime'].includes(kind)) {
        delete formData.end_date;
        delete formData.paid_entry;
        delete formData.permit_category;
        delete formData.paid_beyond_legal_limit;
        delete formData.oncological;
        if (kind !== 'overtime') delete formData.rate_override;
        formData.entry_kind = kind;
        formData.paid = paidEntry.checked;
        await saveWork(formData, recordId);
      } else {
        formData.kind = kind;
        formData.start_date = formData.work_date;
        delete formData.work_date;
        delete formData.location_id;
        delete formData.break_minutes;
        delete formData.rate_override;
        if (kind !== 'permit') delete formData.permit_category;
        delete formData.paid_entry;
        formData.paid = paidEntry.checked;
        formData.paid_beyond_legal_limit = ['permit', 'sickness'].includes(kind)
          ? paidBeyondLegalLimit.checked
          : false;
        formData.oncological = kind === 'sickness'
          ? workForm.querySelector('[name=oncological]').checked
          : false;
        if (['vacation','sickness'].includes(kind)) { delete formData.start_time; delete formData.end_time; }
        await saveAbsence(formData, recordId);
      }
      workDialog.close();
      calendar.refetchEvents();
    } catch (error) { alert(error.message); }
  });
  deleteWorkButton.addEventListener('click', deleteCurrentRecord);
});
