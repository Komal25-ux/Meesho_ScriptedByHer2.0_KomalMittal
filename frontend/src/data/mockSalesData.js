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
//
// Transaction dates are spread as evenly as possible across the 9 weeks the
// range spans (~4-5 transactions/week) rather than tapering off toward June -
// an uneven count-per-week is what made the weekly-aggregated chart read as
// an overall decline even though nothing about the underlying sales was
// actually declining. Week-over-week totals still zigzag naturally (a real
// business has good and bad weeks), but the overall trend is flat-to-up.

export const mockSalesData = [
  { id: 'TXN-001', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 3, revenue: 1287, profit: 387, date: '2025-05-01' },
  { id: 'TXN-002', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 1, revenue: 499, profit: 149, date: '2025-05-04' },
  { id: 'TXN-003', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 6, revenue: 2394, profit: 714, date: '2025-05-05' },
  { id: 'TXN-004', productName: 'White Rayon Top', category: 'tops', quantity: 5, revenue: 1645, profit: 495, date: '2025-05-06' },
  { id: 'TXN-005', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 3, revenue: 897, profit: 297, date: '2025-05-07' },
  { id: 'TXN-006', productName: 'White Rayon Top', category: 'tops', quantity: 5, revenue: 1645, profit: 495, date: '2025-05-09' },
  { id: 'TXN-007', productName: 'Royal Banarasi Silk Saree', category: 'sarees', quantity: 1, revenue: 1499, profit: 449, date: '2025-05-10' },
  { id: 'TXN-008', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 2, revenue: 998, profit: 298, date: '2025-05-11' },
  { id: 'TXN-009', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 4, revenue: 1716, profit: 516, date: '2025-05-13' },
  { id: 'TXN-010', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 7, revenue: 2793, profit: 833, date: '2025-05-16' },
  { id: 'TXN-011', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 1, revenue: 499, profit: 149, date: '2025-05-17' },
  { id: 'TXN-012', productName: 'White Rayon Top', category: 'tops', quantity: 6, revenue: 1974, profit: 594, date: '2025-05-18' },
  { id: 'TXN-013', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 7, revenue: 2793, profit: 833, date: '2025-05-20' },
  { id: 'TXN-014', productName: 'Blue Georgette Saree', category: 'sarees', quantity: 3, revenue: 1497, profit: 477, date: '2025-05-22' },
  { id: 'TXN-015', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 5, revenue: 2145, profit: 645, date: '2025-05-23' },
  { id: 'TXN-016', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 4, revenue: 1196, profit: 396, date: '2025-05-26' },
  { id: 'TXN-017', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 5, revenue: 1995, profit: 595, date: '2025-05-27' },
  { id: 'TXN-018', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 8, revenue: 2392, profit: 792, date: '2025-05-30' },
  { id: 'TXN-019', productName: 'Blue Georgette Saree', category: 'sarees', quantity: 3, revenue: 1497, profit: 477, date: '2025-06-01' },
  { id: 'TXN-020', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 6, revenue: 2394, profit: 714, date: '2025-06-03' },
  { id: 'TXN-021', productName: 'Grand Anarkali Suit', category: 'suits', quantity: 1, revenue: 1199, profit: 359, date: '2025-06-04' },
  { id: 'TXN-022', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 8, revenue: 3192, profit: 952, date: '2025-06-05' },
  { id: 'TXN-023', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 7, revenue: 3003, profit: 903, date: '2025-06-06' },
  { id: 'TXN-024', productName: 'Red Georgette Palazzo Suit', category: 'suits', quantity: 2, revenue: 1598, profit: 498, date: '2025-06-08' },
  { id: 'TXN-025', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 7, revenue: 2793, profit: 833, date: '2025-06-09' },
  { id: 'TXN-026', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 5, revenue: 1995, profit: 595, date: '2025-06-13' },
  { id: 'TXN-027', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 8, revenue: 3432, profit: 1032, date: '2025-06-15' },
  { id: 'TXN-028', productName: 'Black Cotton Kurti and Pant Set', category: 'kurtis', quantity: 2, revenue: 998, profit: 298, date: '2025-06-16' },
  { id: 'TXN-029', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 8, revenue: 3192, profit: 952, date: '2025-06-18' },
  { id: 'TXN-030', productName: 'Basic Blue Cotton Kurti', category: 'kurtis', quantity: 4, revenue: 1596, profit: 476, date: '2025-06-21' },
  { id: 'TXN-031', productName: 'White Rayon Top', category: 'tops', quantity: 4, revenue: 1316, profit: 396, date: '2025-06-22' },
  { id: 'TXN-032', productName: 'Red Silk Bridal Lehenga', category: 'lehengas', quantity: 1, revenue: 2499, profit: 749, date: '2025-06-23' },
  { id: 'TXN-033', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 3, revenue: 897, profit: 297, date: '2025-06-24' },
  { id: 'TXN-034', productName: 'Multicolor Bandhani Saree', category: 'sarees', quantity: 1, revenue: 549, profit: 229, date: '2025-06-25' },
  { id: 'TXN-035', productName: 'Basic Blue Cotton Top', category: 'tops', quantity: 9, revenue: 2691, profit: 891, date: '2025-06-26' },
  { id: 'TXN-036', productName: 'Navy Blue Cotton Kurti', category: 'kurtis', quantity: 9, revenue: 3861, profit: 1161, date: '2025-06-28' },
  { id: 'TXN-037', productName: 'Yellow Cotton Kurti', category: 'kurtis', quantity: 6, revenue: 2394, profit: 714, date: '2025-06-29' },
  { id: 'TXN-038', productName: 'Blue Georgette Saree', category: 'sarees', quantity: 1, revenue: 499, profit: 159, date: '2025-06-30' },
];

export default mockSalesData;
