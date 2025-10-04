### Metrics Dashboard
1. Navigate to **Metrics → Explorer** in Datadog
2. Search for metrics starting with:
   - `repo.*`
   - `ingestion.*`
   - `batch.*`
   - `embeddings.*`
   - `supabase.*`
   - `api.*`

### Creating Custom Dashboards

You can create custom dashboards to monitor:
- Ingestion pipeline performance
- Error rates by component
- Repository processing times
- OpenAI API usage and latency
- Supabase database performance

### Sample Queries

**Average ingestion duration by repository:**
```
avg:ingestion.duration{status:success} by {repo}
```

**Error rate for batch processing:**
```
rate(batch.processing.error{*}.as_count())
```

**OpenAI embedding generation latency (p95):**
```
p95:embeddings.duration{*}
```

## Alerts

Consider setting up alerts for:

1. **High Error Rate**
   - Alert when error rate exceeds threshold
   - Metric: `batch.processing.error`, `ingestion.failed`

2. **Slow Performance**
   - Alert when p95 duration exceeds threshold
   - Metric: `ingestion.duration`, `embeddings.duration`

3. **Failed Repository Clones**
   - Alert on repository clone failures
   - Metric: `repo.clone.error`

4. **API Errors**
   - Alert on API endpoint errors
   - Metric: `api.ingest.error`