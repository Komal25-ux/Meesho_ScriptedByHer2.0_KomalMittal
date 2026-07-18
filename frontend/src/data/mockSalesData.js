// Mock 2-month (May-June) sales history for demo reseller Sunita Didi, for
// future Growth Analytics dashboards. Every productName/selling-price/cost
// pair below is copied verbatim from the real seeded catalog in
// scripts/seed_catalog.py (see build_catalog()) - no invented products.
//
// Quantity follows real reseller economics: cheap daily-wear items (kurtis,
// tops, ~Rs 300-450) sell in bulk per transaction, while premium/occasion
// pieces (bridal lehenga, flagship sarees/suits, Rs 1200+) sell in single
// units but carry a much larger per-unit margin.
//
// revenue = sellingPrice * quantity, profit = (sellingPrice - costPrice) * quantity.

export const mockSalesData = [
  // ── May ──
  { id: 'TXN-001', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 5, revenue: 1995, profit: 595, date: '2025-05-02' },
  { id: 'TXN-002', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 6, revenue: 1794, profit: 594, date: '2025-05-03' },
  { id: 'TXN-003', productName: 'Blue Georgette Saree', category: 'sarees', quantity: 2, revenue: 998, profit: 318, date: '2025-05-04' },
  { id: 'TXN-004', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 4, revenue: 1596, profit: 476, date: '2025-05-05' },
  { id: 'TXN-005', productName: 'Royal Banarasi Silk Saree', category: 'sarees', quantity: 1, revenue: 1499, profit: 449, date: '2025-05-06' },
  { id: 'TXN-006', productName: 'White Rayon Top', category: 'tops', quantity: 5, revenue: 1645, profit: 495, date: '2025-05-07' },
  { id: 'TXN-007', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 3, revenue: 1497, profit: 447, date: '2025-05-08' },
  { id: 'TXN-008', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 4, revenue: 1716, profit: 516, date: '2025-05-09' },
  { id: 'TXN-009', productName: 'Multicolor Bandhani Saree', category: 'sarees', quantity: 2, revenue: 1098, profit: 458, date: '2025-05-11' },
  { id: 'TXN-010', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 6, revenue: 2394, profit: 714, date: '2025-05-12' },
  { id: 'TXN-011', productName: 'Red Georgette Palazzo Suit', category: 'suits', quantity: 1, revenue: 799, profit: 249, date: '2025-05-13' },
  { id: 'TXN-012', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 4, revenue: 1196, profit: 396, date: '2025-05-14' },
  { id: 'TXN-013', productName: 'Red Silk Bridal Lehenga', category: 'lehengas', quantity: 1, revenue: 2499, profit: 749, date: '2025-05-15' },
  { id: 'TXN-014', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 3, revenue: 1197, profit: 357, date: '2025-05-17' },
  { id: 'TXN-015', productName: 'Grand Chikankari Cotton Kurti', category: 'kurtis', quantity: 2, revenue: 1598, profit: 478, date: '2025-05-18' },
  { id: 'TXN-016', productName: 'Blue Georgette Saree', category: 'sarees', quantity: 3, revenue: 1497, profit: 477, date: '2025-05-19' },
  { id: 'TXN-017', productName: 'White Rayon Top', category: 'tops', quantity: 4, revenue: 1316, profit: 396, date: '2025-05-21' },
  { id: 'TXN-018', productName: 'Grand Anarkali Suit', category: 'suits', quantity: 1, revenue: 1199, profit: 359, date: '2025-05-23' },
  { id: 'TXN-019', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 3, revenue: 1287, profit: 387, date: '2025-05-25' },
  { id: 'TXN-020', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 2, revenue: 998, profit: 298, date: '2025-05-27' },
  { id: 'TXN-021', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 4, revenue: 1596, profit: 476, date: '2025-05-28' },
  { id: 'TXN-022', productName: 'Multicolor Bandhani Saree', category: 'sarees', quantity: 3, revenue: 1647, profit: 687, date: '2025-05-30' },

  // ── June ──
  { id: 'TXN-023', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 5, revenue: 1495, profit: 495, date: '2025-06-01' },
  { id: 'TXN-024', productName: 'Royal Banarasi Silk Saree', category: 'sarees', quantity: 1, revenue: 1499, profit: 449, date: '2025-06-02' },
  { id: 'TXN-025', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 6, revenue: 2394, profit: 714, date: '2025-06-03' },
  { id: 'TXN-026', productName: 'Red Georgette Palazzo Suit', category: 'suits', quantity: 2, revenue: 1598, profit: 498, date: '2025-06-05' },
  { id: 'TXN-027', productName: 'White Rayon Top', category: 'tops', quantity: 3, revenue: 987, profit: 297, date: '2025-06-06' },
  { id: 'TXN-028', productName: 'Blue Georgette Saree', category: 'sarees', quantity: 2, revenue: 998, profit: 318, date: '2025-06-08' },
  { id: 'TXN-029', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 7, revenue: 2793, profit: 833, date: '2025-06-09' },
  { id: 'TXN-030', productName: 'Grand Chikankari Cotton Kurti', category: 'kurtis', quantity: 1, revenue: 799, profit: 239, date: '2025-06-11' },
  { id: 'TXN-031', productName: 'Red Silk Bridal Lehenga', category: 'lehengas', quantity: 1, revenue: 2499, profit: 749, date: '2025-06-13' },
  { id: 'TXN-032', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 5, revenue: 2145, profit: 645, date: '2025-06-15' },
  { id: 'TXN-033', productName: 'Multicolor Bandhani Saree', category: 'sarees', quantity: 2, revenue: 1098, profit: 458, date: '2025-06-17' },
  { id: 'TXN-034', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 4, revenue: 1996, profit: 596, date: '2025-06-19' },
  { id: 'TXN-035', productName: 'Grand Anarkali Suit', category: 'suits', quantity: 1, revenue: 1199, profit: 359, date: '2025-06-22' },
  { id: 'TXN-036', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 5, revenue: 1495, profit: 495, date: '2025-06-25' },
  { id: 'TXN-037', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 4, revenue: 1596, profit: 476, date: '2025-06-27' },
  { id: 'TXN-038', productName: 'White Rayon Top', category: 'tops', quantity: 6, revenue: 1974, profit: 594, date: '2025-06-29' },
];

export default mockSalesData;
