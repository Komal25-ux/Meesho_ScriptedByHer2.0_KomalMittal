import React, { useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];
const WEEKDAY_LABELS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

// Same LOCAL-timezone-safe Date.UTC pattern used throughout GrowthDashboard -
// every Date here is built with Date.UTC and read back with getUTC* only.
function parseDateUTC(dateStr) {
  const [y, m, d] = dateStr.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function toDateStrUTC(date) {
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, '0');
  const d = String(date.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

// Inclusive 7-day window starting at dateStr - setUTCDate's own overflow
// handling (day 32 -> next month) means this rolls over month/year boundaries
// correctly with no extra arithmetic.
function weekRangeFrom(dateStr) {
  const start = parseDateUTC(dateStr);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 6);
  return { start: dateStr, end: toDateStrUTC(end) };
}

// Rolling 1-month window starting at dateStr, e.g. 15 Jun -> 15 Jun..15 Jul,
// not the calendar month dateStr happens to fall in. Date.UTC's own month
// overflow normalization handles the year rollover for free (month index 12
// on a December start date normalizes to January of y + 1).
function monthRangeFrom(dateStr) {
  const start = parseDateUTC(dateStr);
  const y = start.getUTCFullYear();
  const m = start.getUTCMonth();
  const day = start.getUTCDate();
  const end = new Date(Date.UTC(y, m + 1, day));
  return { start: dateStr, end: toDateStrUTC(end) };
}

// 6 full weeks (42 cells) starting on the Sunday on/before the 1st of the
// month, so the grid always shows complete weeks including the leading/
// trailing days of adjacent months.
function buildMonthGrid(year, month) {
  const firstOfMonth = new Date(Date.UTC(year, month, 1));
  const gridStart = new Date(firstOfMonth);
  gridStart.setUTCDate(gridStart.getUTCDate() - firstOfMonth.getUTCDay());

  const cells = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(gridStart);
    d.setUTCDate(d.getUTCDate() + i);
    cells.push({
      dateStr: toDateStrUTC(d),
      day: d.getUTCDate(),
      inMonth: d.getUTCMonth() === month
    });
  }
  return cells;
}

// Calendar popover: pick one date, and depending on `timeframe` ('weekly' |
// 'monthly') that click auto-highlights the matching 7-day or full-month
// range. "Done" hands the resolved {start, end} back to the caller.
export default function CalendarRangePicker({ timeframe, initialDate, onDone, onClose }) {
  const initial = initialDate ? parseDateUTC(initialDate) : new Date();
  const [viewYear, setViewYear] = useState(initial.getUTCFullYear());
  const [viewMonth, setViewMonth] = useState(initial.getUTCMonth());
  const [selectedDate, setSelectedDate] = useState(initialDate || null);

  const range = selectedDate
    ? (timeframe === 'monthly' ? monthRangeFrom(selectedDate) : weekRangeFrom(selectedDate))
    : null;

  const cells = buildMonthGrid(viewYear, viewMonth);

  const goPrevMonth = () => {
    const d = new Date(Date.UTC(viewYear, viewMonth - 1, 1));
    setViewYear(d.getUTCFullYear());
    setViewMonth(d.getUTCMonth());
  };
  const goNextMonth = () => {
    const d = new Date(Date.UTC(viewYear, viewMonth + 1, 1));
    setViewYear(d.getUTCFullYear());
    setViewMonth(d.getUTCMonth());
  };

  const isInRange = (dateStr) => !!range && dateStr >= range.start && dateStr <= range.end;

  return (
    <div className="absolute z-50 mt-2 right-0 bg-white border border-[#1E1E24] rounded-[0.5rem] shadow-tactile p-3 w-72 font-['Roboto_Slab',_serif]">
      <div className="flex items-center justify-between mb-2">
        <button type="button" onClick={goPrevMonth} className="p-1 hover:bg-[#F7F7FA] rounded" aria-label="Previous month">
          <ChevronLeft className="w-4 h-4 text-[#1E1E24]" />
        </button>
        <span className="text-xs font-bold text-[#1E1E24]">
          {MONTH_NAMES[viewMonth]} {viewYear}
        </span>
        <button type="button" onClick={goNextMonth} className="p-1 hover:bg-[#F7F7FA] rounded" aria-label="Next month">
          <ChevronRight className="w-4 h-4 text-[#1E1E24]" />
        </button>
      </div>

      <div className="grid grid-cols-7 mb-1">
        {WEEKDAY_LABELS.map((w, i) => (
          <div key={i} className="text-[10px] text-center text-gray-400 font-medium">{w}</div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-y-1">
        {cells.map((cell) => {
          const selected = cell.dateStr === selectedDate;
          const inRange = isInRange(cell.dateStr);
          return (
            <button
              type="button"
              key={cell.dateStr}
              onClick={() => setSelectedDate(cell.dateStr)}
              className={`text-[11px] h-7 w-7 mx-auto rounded-full flex items-center justify-center transition ${
                !cell.inMonth ? 'text-gray-300' : 'text-[#1E1E24]'
              } ${
                selected
                  ? 'bg-[#FC8B16] text-white font-bold'
                  : inRange
                  ? 'bg-[#FC8B16]/20'
                  : 'hover:bg-[#F7F7FA]'
              }`}
            >
              {cell.day}
            </button>
          );
        })}
      </div>

      <p className="text-[10px] text-gray-500 mt-2 mb-2 min-h-[2.2em]">
        {range
          ? timeframe === 'monthly'
            ? `Range: ${range.start} → ${range.end} (1 month)`
            : `Range: ${range.start} → ${range.end} (7 days)`
          : 'Pick a date to preview the range'}
      </p>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="px-3 py-1 text-[11px] font-medium text-[#1E1E24] hover:bg-[#F7F7FA] rounded-[0.4rem]"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => range && onDone(range)}
          disabled={!range}
          className={`px-3 py-1 text-[11px] font-bold rounded-[0.4rem] transition ${
            range ? 'bg-[#FC8B16] text-white hover:opacity-90' : 'bg-gray-200 text-gray-400 cursor-not-allowed'
          }`}
        >
          Done
        </button>
      </div>
    </div>
  );
}
