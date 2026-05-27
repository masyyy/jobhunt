/**
 * Customer-defined named queries for the data API.
 *
 * Each member maps to a registered backend query accessible via
 * GET /api/data/query/{value}. Must stay in sync with
 * backend/customer/queries.py — verified by check_customer_config.py.
 */

export const DashboardQuery = {} as const

export type DashboardQuery = (typeof DashboardQuery)[keyof typeof DashboardQuery]
