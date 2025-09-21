# HM Treasury Spending

![HM Treasury Spending](/assets/hm_treasury_spending_banner.png)

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Data License: OGL v3.0](https://img.shields.io/badge/Data%20License-OGL%20v3.0-blue.svg)
![GitHub Actions](https://img.shields.io/github/actions/workflow/status/SalZaki/hmt-spending/ingest-hmt-spend-data.yml?label=Data%20Update)

## Problem Statement

The HM Treasury publishes spending data (above £25K) across multiple departments in various formats (primarily Excel files) on different schedules. This creates several challenges:

- **Accessibility**: Data is scattered across multiple government websites in non-machine-readable formats
- **Consistency**: Each department may use different formats and field names
- **Historical Analysis**: No easy way to track spending trends over time
- **Transparency Gaps**: Missing supplier details and inconsistent categorization make analysis difficult
- **Integration**: Difficult to combine with other datasets (Companies House, contracts data, etc.)
- **Public Access**: Citizens need technical skills to analyze public spending
- **AI Accessibility**: No structured way for AI agents to query and analyze government spending

This project creates an automated pipeline to collect, standardize, and make HM Treasury spending data easily accessible for analysis, journalism, public accountability, and AI-powered insights.

## Project Phases

### Phase 1: Data Ingestion Pipeline (Current)

- [ ] Automated monthly collection of HM Treasury spending data
- [ ] Convert Excel files to standardized JSON format
- [ ] Store historical data with consistent naming
- [ ] GitHub Actions for scheduled data collection
- [ ] Basic data validation and error handling

### Phase 2: Data Quality & Enrichment

- [ ] Supplier name standardization and deduplication
- [ ] Company registration number lookup via Companies House API
- [ ] Expense category normalization across departments
- [ ] Flag suspicious transactions (unusual amounts, patterns)
- [ ] Add inflation adjustment for historical comparisons
- [ ] Geographic enrichment where postcodes are available
- [ ] Contract reference linking to Contracts Finder data

### Phase 3: Multi-Department Expansion

- [ ] Extend to other major departments (DfE, DoH, MoD, etc.)
- [ ] Unified schema across all departments
- [ ] Cross-department supplier analysis
- [ ] Aggregate spending by supplier across government
- [ ] Framework agreement tracking

### Phase 4: API & Data Access Layer

- [ ] RESTful API for querying spending data
- [ ] GraphQL endpoint for complex queries
- [ ] Static JSON indexes for common queries
- [ ] CSV/Excel export functionality
- [ ] Bulk data downloads with compression
- [ ] API documentation with examples
- [ ] Rate limiting and caching

### Phase 5: MCP Server for AI Agents

- [ ] Model Context Protocol (MCP) server implementation
- [ ] Structured tools for AI queries:
  - `search_spending`: Query by supplier, department, date range
  - `analyze_trends`: Identify spending patterns
  - `compare_suppliers`: Competitive analysis
  - `flag_anomalies`: Detect unusual transactions
  - `summarize_period`: Monthly/quarterly summaries
- [ ] Natural language to query translation
- [ ] Context-aware responses for AI assistants
- [ ] Rate limiting for AI agents
- [ ] Usage analytics and monitoring
- [ ] Example prompts and use cases

### Phase 6: Analytics Dashboard

- [ ] Web application with interactive visualizations
- [ ] Supplier spending league tables
- [ ] Trend analysis and anomaly detection
- [ ] Department comparison tools
- [ ] Search functionality across all transactions
- [ ] Saved queries and watchlists
- [ ] Email alerts for specific suppliers/categories
- [ ] AI-powered insights panel

### Phase 7: Advanced Features

- [ ] Machine learning for expense categorization
- [ ] Predictive analytics for budget forecasting
- [ ] Network analysis of supplier relationships
- [ ] Integration with procurement pipeline data
- [ ] FOI request integration for missing data
- [ ] Crowdsourced data validation
- [ ] Mobile app for on-the-go access

### Phase 8: Accountability Tools

- [ ] Supplier performance metrics
- [ ] Contract value vs actual spend analysis
- [ ] Red flag alerts for procurement issues
- [ ] Journalist toolkit with story leads
- [ ] Public commenting on transactions
- [ ] Integration with parliament questions database

## Technical Stack (Proposed)

**Data Pipeline:**

- Python for data processing
- GitHub Actions for orchestration
- PostgreSQL for data storage
- Redis for caching

**API:**

- FastAPI for REST endpoints
- GraphQL with Strawberry
- OpenAPI documentation

**MCP Server:**

- TypeScript/Python implementation
- JSON-RPC for communication
- Structured tool definitions
- Context management
- Authentication & rate limiting

**Dashboard:**

- Next.js for web application
- D3.js/Recharts for visualizations
- Elasticsearch for search
- Tailwind CSS for styling

**Infrastructure:**

- Docker containers
- GitHub Pages for static data
- Cloudflare CDN
- Vercel/Netlify for web hosting

## MCP Server Tools (Proposed)

```typescript
// Example MCP tool definitions
tools: [
  {
    name: "search_spending",
    description: "Search HM Treasury spending data",
    parameters: {
      supplier?: string,
      department?: string,
      min_amount?: number,
      max_amount?: number,
      start_date?: string,
      end_date?: string,
      expense_type?: string
    }
  },
  {
    name: "analyze_supplier",
    description: "Detailed analysis of a supplier's HM Treasury contracts",
    parameters: {
      supplier_name: string,
      include_subsidiaries?: boolean
    }
  },
  {
    name: "spending_trends",
    description: "Analyze spending trends over time",
    parameters: {
      grouping: "month" | "quarter" | "year",
      category?: string,
      department?: string
    }
  }
]
```

## License

This project is licensed under the MIT License. The data itself is under the Open Government License v3.0.
