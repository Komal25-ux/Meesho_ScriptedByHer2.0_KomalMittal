import React, { useMemo, useState } from 'react';
import { TrendingUp, PieChart as PieChartIcon, Calendar as CalendarIcon, X } from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend
} from 'recharts';
import { mockSalesData } from '../../data/mockSalesData';
import CalendarRangePicker from './CalendarRangePicker';

// "Denim and Industrial Craft" chart palette, cycled if there are more
// categories than colors.
const CATEGORY_COLORS = ['#9F2089', '#FC8B16', '#42BC9E', '#F43397'];

// Anchor date = the latest date present in the dataset (2026-07-19 by
// construction of mockSalesData.js) - derived rather than hardcoded so this
// stays correct if the dataset's range ever changes.
function getAnchorDate(transactions) {
  return transactions.reduce((max, t) => (t.date > max ? t.date : max), transactions[0]?.date ?? '');
}

// Date helpers below deliberately never let a "YYYY-MM-DD" string round-trip
// through JS's LOCAL-timezone Date methods (toISOString()/toLocaleDateString()
// silently shift the calendar day for any user not in a UTC-ish timezone -
// e.g. UTC+5:30 turns local midnight into the previous day in UTC). Every
// Date object here is built with Date.UTC and read back with getUTC* only,
// so day-of-month arithmetic and formatting are 100% timezone-independent.
const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

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

function formatShortLabel(dateStr) {
  const [, m, d] = dateStr.split('-').map(Number);
  return `${d} ${MONTH_SHORT[m - 1]}`;
}

// Returns the last `windowDays` calendar dates (YYYY-MM-DD, oldest first)
// ending at anchorDateStr - the full window regardless of whether a given
// day has any transactions, so zero-sale days still get a real 0-value
// point instead of being skipped.
function lastNDates(anchorDateStr, windowDays) {
  const anchor = parseDateUTC(anchorDateStr);
  const dates = [];
  for (let i = windowDays - 1; i >= 0; i--) {
    const d = new Date(anchor);
    d.setUTCDate(d.getUTCDate() - i);
    dates.push(toDateStrUTC(d));
  }
  return dates;
}

// Every date (YYYY-MM-DD, inclusive) between startStr and endStr - used for
// the custom calendar-picked range, where the caller supplies an explicit
// [start, end] rather than "last N days back from the anchor".
function datesInRange(startStr, endStr) {
  const end = parseDateUTC(endStr);
  const dates = [];
  for (let d = parseDateUTC(startStr); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    dates.push(toDateStrUTC(d));
  }
  return dates;
}

// One point per date in `dates`, zero-filled so the X-axis always plots
// exactly that many points regardless of whether a given day had any sales.
function buildDailyChartDataForDates(transactions, dates) {
  if (dates.length === 0) return [];
  const byDate = new Map();
  for (const txn of transactions) {
    if (!byDate.has(txn.date)) byDate.set(txn.date, { sales: 0, profit: 0, quantity: 0 });
    const bucket = byDate.get(txn.date);
    bucket.sales += txn.revenue;
    bucket.profit += txn.profit;
    bucket.quantity += txn.quantity;
  }

  return dates.map((dateStr) => {
    const agg = byDate.get(dateStr) || { sales: 0, profit: 0, quantity: 0 };
    return { day: formatShortLabel(dateStr), ...agg };
  });
}

// Weekly = last 7 days, Monthly = last 30 days, both ending at the anchor.
function buildDailyChartData(transactions, windowDays) {
  if (transactions.length === 0) return [];
  const anchor = getAnchorDate(transactions);
  return buildDailyChartDataForDates(transactions, lastNDates(anchor, windowDays));
}

// Category totals (Sales ₹ or Quantity, matching the metric toggle) for an
// explicit [startStr, endStr] window - what keeps the pie chart in sync with
// whatever range the line chart above it is showing, custom or not.
function buildCategoryBreakdownForRange(transactions, startStr, endStr, metric) {
  const totals = new Map();
  for (const txn of transactions) {
    if (txn.date < startStr || txn.date > endStr) continue;
    const value = metric === 'quantity' ? txn.quantity : txn.revenue;
    totals.set(txn.category, (totals.get(txn.category) || 0) + value);
  }

  return [...totals.entries()]
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));
}

// Weekly = last 7 days, Monthly = last 30 days, both ending at the anchor.
function buildCategoryBreakdown(transactions, windowDays, metric) {
  if (transactions.length === 0) return [];
  const anchor = getAnchorDate(transactions);
  const windowStart = lastNDates(anchor, windowDays)[0];
  return buildCategoryBreakdownForRange(transactions, windowStart, anchor, metric);
}

function SegmentedToggle({ options, value, onChange }) {
  return (
    <div className="inline-flex border border-[#1E1E24] rounded-[0.5rem] overflow-hidden shrink-0">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1 text-[11px] font-['Roboto_Slab',_serif] font-medium whitespace-nowrap transition ${
            value === opt.value
              ? 'bg-[#FC8B16] text-white'
              : 'bg-white text-[#1E1E24] hover:bg-[#F7F7FA]'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

const tooltipStyle = {
  contentStyle: { backgroundColor: '#1E1E24', border: '1px solid #000', borderRadius: '6px', fontSize: '11px', fontFamily: 'monospace' },
  labelStyle: { color: '#FFFFFF', fontWeight: 'bold' },
  itemStyle: { color: '#FFFFFF' }
};

// en-IN comma formatting for every revenue/profit/sales number rendered in
// this dashboard, so ₹54090 always reads as ₹54,090 (also what makes TTS
// read the same number aloud as a whole word instead of digit-by-digit -
// see prompt_growth_agent.md).
const inr = (value) => Number(value).toLocaleString('en-IN');

// Pie slices only carry their own value, not the whole-chart total, so the
// percentage share has to be computed here from the full categoryData array
// passed in as a prop - can't be derived from `payload` alone since Recharts
// only hands the hovered slice to the tooltip.
function PieTooltip({ active, payload, total, metric }) {
  if (!active || !payload || !payload.length) return null;
  const { name, value } = payload[0];
  const share = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0';
  const formattedValue = metric === 'sales' ? `₹${inr(value)}` : inr(value);
  return (
    <div style={tooltipStyle.contentStyle}>
      <p style={{ ...tooltipStyle.labelStyle, margin: 0 }}>{name}</p>
      <p style={{ ...tooltipStyle.itemStyle, margin: 0 }}>{formattedValue} ({share}%)</p>
    </div>
  );
}

export default function GrowthDashboard() {
  const [timeframe, setTimeframe] = useState('weekly'); // 'weekly' | 'monthly'
  const [metric, setMetric] = useState('sales'); // 'sales' | 'quantity'
  const windowDays = timeframe === 'weekly' ? 7 : 30;

  // Custom calendar-picked range overrides the rolling Weekly/Monthly window
  // until cleared or the toggle is changed again. { start, end } | null.
  const [customRange, setCustomRange] = useState(null);
  const [showCalendar, setShowCalendar] = useState(false);

  // Switching the Weekly/Monthly toggle exits custom-range mode - the two
  // are alternate ways to pick a window, not layered on top of each other.
  const handleTimeframeChange = (value) => {
    setTimeframe(value);
    setCustomRange(null);
  };

  const chartData = useMemo(() => {
    if (customRange) {
      return buildDailyChartDataForDates(mockSalesData, datesInRange(customRange.start, customRange.end));
    }
    return buildDailyChartData(mockSalesData, windowDays);
  }, [windowDays, customRange]);

  const categoryData = useMemo(() => {
    if (customRange) {
      return buildCategoryBreakdownForRange(mockSalesData, customRange.start, customRange.end, metric);
    }
    return buildCategoryBreakdown(mockSalesData, windowDays, metric);
  }, [windowDays, metric, customRange]);

  const categoryTotal = useMemo(
    () => categoryData.reduce((sum, entry) => sum + entry.value, 0),
    [categoryData]
  );

  // Long ranges (Monthly toggle, or a custom range spanning > 10 days) get
  // the rotated/sparser X-axis labels; short ranges get one label per day.
  const isLongRange = chartData.length > 10;

  return (
    <div className="h-full overflow-y-auto pb-8">
      <div className="bg-meesho-white border border-meesho-dark rounded-xl p-4 shadow-tactile">
        {/* Header row: title left, Weekly/Monthly toggle next to it, Sales/Quantity toggle pinned right */}
        <div className="flex justify-between items-center w-full gap-2 flex-wrap mb-4">
          <div className="flex items-center gap-2 min-w-0">
            <h3 className="text-sm font-bold text-meesho-dark flex items-center whitespace-nowrap">
              <TrendingUp className="w-4 h-4 text-meesho-teal mr-1.5 shrink-0" />
              Didi Sales Performance Chart
            </h3>
            <SegmentedToggle
              options={[
                { value: 'weekly', label: 'Weekly' },
                { value: 'monthly', label: 'Monthly' }
              ]}
              value={timeframe}
              onChange={handleTimeframeChange}
            />
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                type="button"
                onClick={() => setShowCalendar((v) => !v)}
                className={`p-1.5 border border-[#1E1E24] rounded-[0.5rem] transition ${
                  customRange ? 'bg-[#FC8B16] text-white' : 'bg-white text-[#1E1E24] hover:bg-[#F7F7FA]'
                }`}
                aria-label="Pick a custom date range"
                title={customRange ? `Custom range: ${customRange.start} → ${customRange.end}` : 'Pick a custom date range'}
              >
                <CalendarIcon className="w-4 h-4" />
              </button>
              {showCalendar && (
                <CalendarRangePicker
                  timeframe={timeframe}
                  initialDate={customRange?.start ?? null}
                  onClose={() => setShowCalendar(false)}
                  onDone={(range) => {
                    setCustomRange(range);
                    setShowCalendar(false);
                  }}
                />
              )}
            </div>
            <SegmentedToggle
              options={[
                { value: 'sales', label: 'Sales' },
                { value: 'quantity', label: 'Quantity' }
              ]}
              value={metric}
              onChange={setMetric}
            />
          </div>
        </div>

        {customRange && (
          <div className="flex items-center gap-1.5 -mt-2 mb-3 text-[11px] font-mono text-[#1E1E24]">
            <span>Custom range: {customRange.start} → {customRange.end}</span>
            <button
              type="button"
              onClick={() => setCustomRange(null)}
              className="p-0.5 hover:bg-[#F7F7FA] rounded"
              aria-label="Clear custom range"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        {/* Line/Area Chart - exactly `windowDays` points, one per calendar day */}
        <div className="flex justify-center items-center w-full h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="colorSales" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#9F2089" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#9F2089" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorProfit" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#42BC9E" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#42BC9E" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorQuantity" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#FC8B16" stopOpacity={0.8} />
                  <stop offset="95%" stopColor="#FC8B16" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="day"
                stroke="#1E1E24"
                style={{ fontSize: '9px', fontFamily: 'monospace' }}
                interval={isLongRange ? 3 : 0}
                angle={isLongRange ? -45 : 0}
                textAnchor={isLongRange ? 'end' : 'middle'}
                height={isLongRange ? 40 : 30}
              />
              <YAxis
                stroke="#1E1E24"
                style={{ fontSize: '10px', fontFamily: 'monospace' }}
                label={{
                  value: metric === 'sales' ? 'Amount (₹)' : 'Number of Articles',
                  angle: -90,
                  position: 'insideLeft',
                  style: { fontSize: '9px', fontFamily: 'monospace', fill: '#1E1E24' }
                }}
              />
              <Tooltip {...tooltipStyle} formatter={(value, name) => [metric === 'sales' ? `₹${inr(value)}` : inr(value), name]} />
              {metric === 'sales' ? (
                <>
                  <Area type="monotone" dataKey="sales" name="Sales (₹)" stroke="#9F2089" fillOpacity={1} fill="url(#colorSales)" />
                  <Area type="monotone" dataKey="profit" name="Profit (₹)" stroke="#42BC9E" fillOpacity={1} fill="url(#colorProfit)" />
                </>
              ) : (
                <Area type="monotone" dataKey="quantity" name="Quantity" stroke="#FC8B16" fillOpacity={1} fill="url(#colorQuantity)" />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Category Breakdown - same timeframe + metric toggles as above */}
      <div className="bg-meesho-white border border-meesho-dark rounded-xl p-4 shadow-tactile mt-4">
        <h3 className="text-sm font-bold text-meesho-dark flex items-center mb-4">
          <PieChartIcon className="w-4 h-4 text-meesho-jamuni mr-1.5 shrink-0" />
          Category Breakdown
        </h3>
        <div className="flex justify-center items-center w-full h-64">
          {categoryData.length === 0 ? (
            <p className="text-xs text-gray-500 font-mono">No sales in this period.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={categoryData}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="45%"
                  outerRadius="75%"
                  paddingAngle={2}
                >
                  {categoryData.map((entry, index) => (
                    <Cell key={entry.name} fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]} />
                  ))}
                </Pie>
                <Legend wrapperStyle={{ fontSize: '11px', fontFamily: 'monospace', color: '#1E1E24' }} />
                <Tooltip content={<PieTooltip total={categoryTotal} metric={metric} />} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
