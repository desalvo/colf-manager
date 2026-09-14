let calendar;
const workDialog = document.getElementById('workDialog');
const workForm = document.getElementById('workForm');
const deleteWorkButton = document.getElementById('deleteWorkButton');

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

function resetWorkForm() {
  workForm.reset();
  workForm.querySelector('[name=entry_id]').value = '';
  workForm.querySelector('[name=start_time]').value = '09:00';
  workForm.querySelector('[name=end_time]').value = '13:00';
  workForm.querySelector('[name=break_minutes]').value = '0';
  document.getElementById('workDialogTitle').textContent = 'Registra ore';
  deleteWorkButton.classList.add('hidden');
}

function openWorkModal(day, startTime) {
  resetWorkForm();
  const chosen = day || localDateString(calendar.getDate());
  workForm.querySelector('[name=work_date]').value = chosen;
  if (startTime) {
    workForm.querySelector('[name=start_time]').value = startTime;
    const [hour, minute] = startTime.split(':').map(Number);
    const end = new Date(2000, 0, 1, hour, minute + 60);
    workForm.querySelector('[name=end_time]').value = timeString(end);
  }
  workDialog.showModal();
}

function openEditModal(event) {
  if (event.extendedProps.type !== 'work') return;
  resetWorkForm();
  workForm.querySelector('[name=entry_id]').value = event.id.replace('work-', '');
  workForm.querySelector('[name=worker_id]').value = event.extendedProps.worker_id;
  workForm.querySelector('[name=work_date]').value = event.startStr.slice(0, 10);
  workForm.querySelector('[name=start_time]').value = event.startStr.slice(11, 16);
  workForm.querySelector('[name=end_time]').value = event.endStr.slice(11, 16);
  workForm.querySelector('[name=location_id]').value = event.extendedProps.location_id || '';
  workForm.querySelector('[name=break_minutes]').value = event.extendedProps.break_minutes || 0;
  workForm.querySelector('[name=notes]').value = event.extendedProps.notes || '';
  document.getElementById('workDialogTitle').textContent = 'Modifica registrazione ore';
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

async function deleteCurrentWork() {
  const entryId = workForm.querySelector('[name=entry_id]').value;
  if (!entryId || !confirm('Eliminare definitivamente questa registrazione di ore?')) return;
  const response = await fetch(`/api/work/${entryId}`, {
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
    eventData: (el) => ({
      title: el.querySelector('strong')?.textContent || 'Ore',
      duration: {minutes: Number(el.dataset.duration || 60)},
      backgroundColor: getComputedStyle(el).getPropertyValue('--event-color').trim(),
      borderColor: getComputedStyle(el).getPropertyValue('--event-color').trim(),
      extendedProps: {
        quickPattern: true,
        worker_id: el.dataset.workerId,
        location_id: el.dataset.locationId,
        break_minutes: el.dataset.break,
        duration_minutes: el.dataset.duration,
      },
    }),
  });
}

document.addEventListener('DOMContentLoaded', () => {
  calendar = new FullCalendar.Calendar(document.getElementById('calendar'), {
    initialView: 'timeGridWeek',
    locale: 'it',
    firstDay: 1,
    editable: true,
    selectable: true,
    droppable: true,
    nowIndicator: true,
    allDaySlot: true,
    slotDuration: '00:30:00',
    slotMinTime: '06:00:00',
    slotMaxTime: '23:00:00',
    height: 'auto',
    expandRows: true,
    eventMinHeight: 28,
    eventTimeFormat: {hour: '2-digit', minute: '2-digit', hour12: false},
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek,timeGridDay',
    },
    buttonText: {today: 'Oggi', month: 'Mese', week: 'Settimana', day: 'Giorno'},
    events: (info, ok, fail) => fetch(`/api/events?worker_id=${document.getElementById('workerFilter').value}`)
      .then((response) => response.json()).then(ok).catch(fail),
    dateClick: (info) => {
      const startTime = info.allDay ? null : timeString(info.date);
      openWorkModal(info.dateStr.slice(0, 10), startTime);
    },
    eventClick: (info) => openEditModal(info.event),
    eventDrop: async (info) => {
      if (!info.event.id.startsWith('work-')) return info.revert();
      try {
        await saveWork({
          work_date: info.event.startStr.slice(0, 10),
          start_time: info.event.startStr.slice(11, 16),
          end_time: info.event.endStr?.slice(11, 16),
        }, info.event.id.replace('work-', ''));
      } catch (error) {
        alert(error.message);
        info.revert();
      }
    },
    eventResize: async (info) => {
      if (!info.event.id.startsWith('work-')) return info.revert();
      try {
        await saveWork({
          work_date: info.event.startStr.slice(0, 10),
          start_time: info.event.startStr.slice(11, 16),
          end_time: info.event.endStr?.slice(11, 16),
        }, info.event.id.replace('work-', ''));
      } catch (error) {
        alert(error.message);
        info.revert();
      }
    },
    eventReceive: async (info) => {
      const props = info.event.extendedProps;
      if (!props.quickPattern) return;
      try {
        const end = info.event.end || addMinutes(info.event.start, props.duration_minutes || 60);
        await saveWork({
          worker_id: props.worker_id,
          location_id: props.location_id,
          work_date: localDateString(info.event.start),
          start_time: timeString(info.event.start),
          end_time: timeString(end),
          break_minutes: props.break_minutes || 0,
        });
        info.event.remove();
        calendar.refetchEvents();
      } catch (error) {
        alert(error.message);
        info.event.remove();
      }
    },
    eventContent: (arg) => {
      if (arg.event.extendedProps.type !== 'work') return undefined;
      const props = arg.event.extendedProps;
      const wrap = document.createElement('div');
      const isMonth = arg.view.type === 'dayGridMonth';
      wrap.className = isMonth ? 'calendar-event-content month-compact' : 'calendar-event-content';
      if (isMonth) {
        const start = arg.event.start ? timeString(arg.event.start) : '';
        const end = arg.event.end ? timeString(arg.event.end) : '';
        wrap.textContent = end ? `${start}–${end}` : start;
      } else {
        wrap.innerHTML = `<b>${arg.timeText}</b><span>${props.worker}</span><small>${props.employer}</small><small>${props.location}</small>`;
      }
      return {domNodes: [wrap]};
    },
    eventDidMount: (info) => {
      if (info.event.extendedProps.type !== 'work') return;
      const props = info.event.extendedProps;
      const start = info.event.start ? timeString(info.event.start) : '';
      const end = info.event.end ? timeString(info.event.end) : '';
      const details = [
        `${start}${end ? `–${end}` : ''}`,
        `Lavoratore: ${props.worker || '—'}`,
        `Datore: ${props.employer || '—'}`,
        `Luogo: ${props.location || '—'}`,
      ].join('\n');
      info.el.title = details;
      info.el.setAttribute('aria-label', details.replaceAll('\n', '. '));
      info.el.tabIndex = 0;
    },
  });
  calendar.render();
  initExternalPatterns();
  document.getElementById('workerFilter').addEventListener('change', () => calendar.refetchEvents());

  workForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = Object.fromEntries(new FormData(workForm));
    const entryId = formData.entry_id;
    delete formData.entry_id;
    try {
      await saveWork(formData, entryId);
      workDialog.close();
      calendar.refetchEvents();
    } catch (error) {
      alert(error.message);
    }
  });
  deleteWorkButton.addEventListener('click', deleteCurrentWork);
});
