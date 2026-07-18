import React from 'react';

/**
 * "Denim and Industrial Craft" price patch - replaces the old AI-generated
 * price overlay baked into the product image. Renders as a stitched fabric
 * patch sitting directly below the product photo instead.
 */
export default function PricePatch({ price }) {
  if (price === undefined || price === null || price === '') return null;

  return (
    <div
      className="
        inline-flex items-center gap-2
        px-3 py-1.5
        bg-[#F7F7FA]
        rounded-[0.5rem]
        border-dashed border-2 border-[#F43397]
        shadow-md
      "
    >
      <span className="bg-[#42BC9E] w-2 h-2 rounded-full shrink-0" aria-hidden="true" />
      <span className="font-['Roboto_Slab',_serif] font-bold text-lg sm:text-xl text-[#1E1E24]">
        ₹{price}
      </span>
    </div>
  );
}
