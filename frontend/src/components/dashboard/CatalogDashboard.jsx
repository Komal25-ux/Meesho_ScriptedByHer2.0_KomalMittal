import React, { useMemo, useState } from 'react';
import { mockSalesData } from '../../data/mockSalesData';
import { catalogData } from '../../data/catalogData';

// Aggregates the 60-day transaction log by productName - this is the same
// "Python/JS computes, model/UI only renders" split used by the Growth
// Dashboard's chart data: totals are derived here, not re-derived per card.
// Every productName in mockSalesData is copied verbatim from the seeded
// catalog (see mockSalesData.js's own header comment), so this lookup
// resolves the real product photo for a past-order card instead of a dead
// via.placeholder.com link (the service was discontinued in 2024).
const IMAGE_BY_PRODUCT_NAME = new Map(catalogData.map((p) => [p.name, p.imageUrl]));

function aggregatePastOrders(transactions) {
  const byProduct = new Map();
  for (const txn of transactions) {
    if (!byProduct.has(txn.productName)) {
      byProduct.set(txn.productName, {
        productName: txn.productName,
        category: txn.category,
        totalArticlesSold: 0,
        totalProfit: 0,
        totalRevenue: 0
      });
    }
    const bucket = byProduct.get(txn.productName);
    bucket.totalArticlesSold += txn.quantity;
    bucket.totalProfit += txn.profit;
    bucket.totalRevenue += txn.revenue;
  }
  return [...byProduct.values()];
}

function SegmentedToggle({ options, value, onChange }) {
  return (
    <div className="inline-flex border border-[#1E1E24] rounded-[0.5rem] overflow-hidden shrink-0">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1.5 text-xs font-['Roboto_Slab',_serif] font-medium whitespace-nowrap transition ${
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

function PastOrderCard({ product, isTopSeller, isTopProfit }) {
  const glow = isTopSeller || isTopProfit;
  // Selling price isn't tracked per-transaction in mockSalesData - derived
  // here from the same product's revenue/quantity ratio, the actual average
  // per-unit price the reseller sold at over the window.
  const sellingPrice = Math.round(product.totalRevenue / product.totalArticlesSold);

  return (
    <div
      className={`bg-white rounded-lg border border-gray-200 p-3 transition ${
        glow ? 'ring-2 ring-[#42BC9E] shadow-[0_0_15px_rgba(66,188,158,0.5)]' : ''
      }`}
    >
      <h4 className="text-xs font-bold text-meesho-dark truncate mb-2" title={product.productName}>
        {product.productName}
      </h4>
      <div className="w-full aspect-square rounded-md overflow-hidden bg-gray-100 mb-2">
        <img
          src={IMAGE_BY_PRODUCT_NAME.get(product.productName) || 'https://placehold.co/150x150'}
          alt={product.productName}
          className="w-full h-full object-cover"
        />
      </div>
      <p className="text-xs text-meesho-dark font-semibold">₹{sellingPrice}</p>
      <p className="text-[11px] text-gray-500">Sold: {product.totalArticlesSold} units</p>
      <p className="text-[11px] text-meesho-teal font-medium">Profit: ₹{product.totalProfit.toLocaleString('en-IN')}</p>
    </div>
  );
}

function CatalogCard({ product }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-3">
      <h4 className="text-xs font-bold text-meesho-dark truncate mb-2" title={product.name}>
        {product.name}
      </h4>
      <div className="w-full aspect-square rounded-md overflow-hidden bg-gray-100 mb-2">
        <img src={product.imageUrl} alt={product.name} className="w-full h-full object-cover" />
      </div>
      <p className="text-[11px] text-gray-500">Your Cost: ₹{product.costPrice}</p>
    </div>
  );
}

export default function CatalogDashboard() {
  const [view, setView] = useState('past'); // 'past' | 'catalog'

  const pastOrders = useMemo(() => aggregatePastOrders(mockSalesData), []);

  const { maxArticlesSold, maxProfit } = useMemo(() => {
    if (pastOrders.length === 0) return { maxArticlesSold: 0, maxProfit: 0 };
    return {
      maxArticlesSold: Math.max(...pastOrders.map((p) => p.totalArticlesSold)),
      maxProfit: Math.max(...pastOrders.map((p) => p.totalProfit))
    };
  }, [pastOrders]);

  return (
    <div className="h-full overflow-y-auto pb-8">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-sm font-bold text-meesho-dark">Catalog</h3>
        <SegmentedToggle
          options={[
            { value: 'past', label: 'Past Orders' },
            { value: 'catalog', label: "Meesho's Catalog" }
          ]}
          value={view}
          onChange={setView}
        />
      </div>

      {view === 'past' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {pastOrders.map((product) => (
            <PastOrderCard
              key={product.productName}
              product={product}
              isTopSeller={product.totalArticlesSold === maxArticlesSold}
              isTopProfit={product.totalProfit === maxProfit}
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {catalogData.map((product) => (
            <CatalogCard key={product.productId} product={product} />
          ))}
        </div>
      )}
    </div>
  );
}
