import React from 'react';

/**
 * "Denim and Industrial Craft" product picker - renders the 2-4 ambiguous
 * SKU matches an agent returns instead of silently auto-drafting/answering
 * from whichever match ranked first. Tapping a card sends that product's
 * exact name back as the next chat message (see onSelect), which the
 * backend resolves deterministically (see check_pending_selection in
 * orchestrator.py) instead of re-running an ambiguous search.
 */
export default function ProductGrid({ products, onSelect }) {
  if (!products || products.length === 0) return null;

  return (
    <div className="mt-3 -mx-4 grid grid-cols-2 gap-2">
      {products.map((product, idx) => (
        <button
          key={product.name ? `${product.name}-${idx}` : idx}
          type="button"
          onClick={() => onSelect?.(product.name)}
          className="
            flex flex-col gap-1.5 text-left p-2
            bg-[#F7F7FA] rounded-[0.5rem]
            border border-gray-200
            shadow-[0_2px_12px_rgba(0,0,0,0.06)]
            hover:bg-gray-50 hover:shadow-[0_4px_16px_rgba(0,0,0,0.1)]
            active:translate-y-[1px]
            transition-all duration-200
          "
        >
          <span className="font-['Roboto_Slab',_serif] font-medium text-sm text-[#1E1E24] truncate line-clamp-1">
            {product.name}
          </span>

          <img
            src={product.base_image_url}
            alt={product.name}
            className="aspect-square w-full object-cover rounded-sm"
          />

          <span className="font-['Roboto_Slab',_serif] font-bold text-base sm:text-lg text-[#1E1E24]">
            ₹{product.price}
          </span>
        </button>
      ))}
    </div>
  );
}
