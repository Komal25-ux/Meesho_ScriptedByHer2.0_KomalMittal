import React, { useMemo, useState } from 'react';
import { TrendingUp } from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip
} from 'recharts';
import { mockSalesData } from '../../data/mockSalesData';

// Groups mockSalesData's real transaction history into weekly or monthly
// {day, sales, profit, quantity} buckets. Weekly buckets are anchored to the
// first transaction's date (7-day windows from there); monthly buckets group
// by calendar month - with only May/June in the dataset, Monthly shows 2
// points, which is the honest picture for a 2-month demo history.
function buildPeriodChartData(transactions, period) {
  if (transactions.length === 0) return [];
  const sorted = [...transactions].sort((a, b) => a.date.localeCompare(b.date));
  const firstDate = new Date(`${sorted[0].date}T00:00:00`);

  const buckets = new Map();
  for (const txn of sorted) {
    const txnDate = new Date(`${txn.date}T00:00:00`);
    let key, order, label;

    if (period === 'monthly') {
      key = `${txnDate.getFullYear()}-${txnDate.getMonth()}`;
      order = txnDate.getFullYear() * 12 + txnDate.getMonth();
      label = txnDate.toLocaleDateString('en-IN', { month: 'long' });
    } else {
      const daysSinceStart = Math.round((txnDate - firstDate) / 86400000);
      const weekIndex = Math.floor(daysSinceStart / 7);
      const weekStart = new Date(firstDate);
      weekStart.setDate(weekStart.getDate() + weekIndex * 7);
      key = weekIndex;
      order = weekIndex;
      label = weekStart.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
    }

    if (!buckets.has(key)) buckets.set(key, { order, label, sales: 0, profit: 0, quantity: 0 });
    const bucket = buckets.get(key);
    bucket.sales += txn.revenue;
    bucket.profit += txn.profit;
    bucket.quantity += txn.quantity;
  }

  return [...buckets.values()]
    .sort((a, b) => a.order - b.order)
    .map(({ label, sales, profit, quantity }) => ({ day: label, sales, profit, quantity }));
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

export default function GrowthDashboard() {
  const [timeframe, setTimeframe] = useState('weekly'); // 'weekly' | 'monthly'
  const [metric, setMetric] = useState('sales'); // 'sales' | 'quantity'

  const chartData = useMemo(
    () => buildPeriodChartData(mockSalesData, timeframe),
    [timeframe]
  );

  return (
    <div className="h-full bg-meesho-white border border-meesho-dark rounded-xl p-4 shadow-tactile flex flex-col overflow-hidden">
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

      {/* Responsive Chart */}
      <div className="flex justify-center items-center w-full flex-1 min-h-0">
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
            <XAxis dataKey="day" stroke="#1E1E24" style={{ fontSize: '10px', fontFamily: 'monospace' }} />
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
            <Tooltip
              contentStyle={{ backgroundColor: '#1E1E24', border: '1px solid #000', borderRadius: '6px', fontSize: '11px', fontFamily: 'monospace' }}
              labelStyle={{ color: '#FFFFFF', fontWeight: 'bold' }}
              itemStyle={{ color: '#FFFFFF' }}
              formatter={(value, name) => [metric === 'sales' ? `₹${value}` : value, name]}
            />
            {metric === 'sales' ? (
              <>
                <Area type="monotone" dataKey="sales" name="Sales (₹)" stroke="#9F2089" fillOpacity={1} fill="url(#colorSales)" />
                <Area type="monotone" dataKey="profit" name="Margin (₹)" stroke="#42BC9E" fillOpacity={1} fill="url(#colorProfit)" />
              </>
            ) : (
              <Area type="monotone" dataKey="quantity" name="Quantity" stroke="#FC8B16" fillOpacity={1} fill="url(#colorQuantity)" />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
