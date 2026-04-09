# Runbook: GraphQL Performance Issues

## Severity: P2 (P1 if response times > 30s)

## Symptoms
- GraphQL query response times > 5 seconds (P99)
- High CPU usage on application servers
- Database CPU at >80% utilization
- Customer-facing pages loading slowly or timing out
- Increased error rate from downstream clients timing out

## Impact
- Degraded user experience across all storefronts
- Potential cascade failure if timeouts trigger retries
- SEO impact if pages are slow for search engine bots

## Triage Steps

### Step 1: Identify slow queries
```bash
# Application-level slow query log
grep "QUERY_TIME_EXCEEDED" /var/log/saleor/graphql.log | tail -20

# PostgreSQL slow query log
grep "duration:" /var/log/postgresql/postgresql.log | sort -t: -k4 -rn | head -20
```

### Step 2: Common culprits

#### A. Products query with deep nesting
```graphql
# This query causes N+1 issues:
query {
  products(first: 100) {
    edges {
      node {
        variants { 
          stocks { 
            warehouse { name }
          }
        }
        images { url }
        attributes { attribute { name } values { name } }
      }
    }
  }
}
```
**Fix:** Limit query depth using `GRAPHQL_QUERY_MAX_COMPLEXITY` setting.

#### B. Orders query without date filter
```graphql
# This scans the entire orders table:
query { orders(first: 50) { edges { node { id } } } }
```
**Fix:** Always filter by date range: `orders(filter: { created: { gte: "2024-01-01" } })`

#### C. Missing database indexes
```sql
-- Check for missing indexes on commonly queried columns
SELECT schemaname, tablename, indexname FROM pg_indexes 
WHERE tablename IN ('order_order', 'checkout_checkout', 'payment_payment')
ORDER BY tablename;
```

### Step 3: Immediate mitigation
1. Enable query cost limiting:
   ```python
   GRAPHQL_QUERY_MAX_COMPLEXITY = 50000
   GRAPHQL_QUERY_MAX_DEPTH = 15
   ```
2. Clear Django cache: `python manage.py clear_cache`
3. Restart celery workers (they may be consuming DB connections)
4. If DB CPU > 90%: Kill long-running queries:
   ```sql
   SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE query_start < now() - interval '60 seconds' 
   AND state = 'active';
   ```

### Step 4: Long-term fixes
1. Add DataLoaders for N+1 query patterns
2. Implement query result caching in Redis
3. Add database read replicas for query load
4. Review and optimize slow queries with `EXPLAIN ANALYZE`

## Escalation
- If avg response time > 10s → P1
- If database disk space > 90% → P1 (potential crash)
- If affecting payment processing → P1 + notify payments team
