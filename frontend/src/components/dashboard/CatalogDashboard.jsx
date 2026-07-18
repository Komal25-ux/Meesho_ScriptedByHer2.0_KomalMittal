import React from 'react';
import { Layers } from 'lucide-react';

// Placeholder for the reseller's own listings grid (image/name/price/stock,
// per ideas.txt) - not yet built. Renders under the "Reseller's Catalog" tab
// so the tab has somewhere to land; the actual grid is a separate task.
export default function CatalogDashboard() {
  return (
    <div className="h-full bg-meesho-white border border-meesho-dark rounded-xl p-4 shadow-tactile flex flex-col items-center justify-center text-center overflow-hidden">
      <Layers className="w-8 h-8 text-meesho-jamuni opacity-40 mb-3" />
      <h3 className="text-sm font-bold text-meesho-dark mb-1">Reseller's Catalog</h3>
      <p className="text-[11px] text-gray-500 max-w-xs">
        Your live listings grid is coming soon - image, price, and stock status for every item you've posted.
      </p>
    </div>
  );
}
