import React, { useMemo, useState } from 'react';
import { TrendingUp, PieChart as PieChartIcon } from 'lucide-react';
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

// One point per calendar day in the last `windowDays` days - Weekly = 7,
// Monthly = 30 - zero-filled so the X-axis always plots exactly that many
// points, matching what the Weekly/Monthly toggle promises.
function buildDailyChartData(transactions, windowDays) {
  if (transactions.length === 0) return [];
  const anchor = getAnchorDate(transactions);
  const dates = lastNDates(anchor, windowDays);

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

// Category totals (Sales ₹ or Quantity, matching the metric toggle) for the
// SAME last-7/last-30-day window the line chart is showing - this is what
// keeps the pie chart "timeframe-synced" instead of always summarizing the
// full 2-month history regardless of which toggle is selected.
function buildCategoryBreakdown(transactions, windowDays, metric) {
  if (transactions.length === 0) return [];
  const anchor = getAnchorDate(transactions);
  const windowStart = lastNDates(anchor, windowDays)[0];

  const totals = new Map();
  for (const txn of transactions) {
    if (txn.date < windowStart || txn.date > anchor) continue;
    const value = metric === 'quantity' ? txn.quantity : txn.revenue;
    totals.set(txn.category, (totals.get(txn.category) || 0) + value);
  }

  return [...totals.entries()]
    .filter(([, value]) => value > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));
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

  const chartData = useMemo(
    () => buildDailyChartData(mockSalesData, windowDays),
    [windowDays]
  );
  const categoryData = useMemo(
    () => buildCategoryBreakdown(mockSalesData, windowDays, metric),
    [windowDays, metric]
  );
  const categoryTotal = useMemo(
    () => categoryData.reduce((sum, entry) => sum + entry.value, 0),
    [categoryData]
  );

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
              onChange={setTimeframe}
            />
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
                interval={timeframe === 'monthly' ? 3 : 0}
                angle={timeframe === 'monthly' ? -45 : 0}
                textAnchor={timeframe === 'monthly' ? 'end' : 'middle'}
                height={timeframe === 'monthly' ? 40 : 30}
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
