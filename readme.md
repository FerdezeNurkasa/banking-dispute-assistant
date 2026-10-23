# Banking Dispute Assistant: a multi-agent AI system

A full-stack, agentic AI application that helps a bank handle **card transaction disputes**
("I was charged twice", "I didn't make this purchase", "I cancelled but was still charged").

A team of AI agents built with **LangGraph** investigates each dispute using tools, checks fraud risk and bank policy in
parallel, and drafts a decision. Risky cases are routed to a **human reviewer**, and every step is written to an
**audit trail**.

**Stack:** Python · FastAPI · LangChain · LangGraph · OpenAI · React · PostgreSQL · OpenSearch · Docker · AWS Lambda · API Gateway

## Architecture

```
React (Vite)  ──►  API Gateway  ──►  Lambda (FastAPI + Mangum, Docker image)
                                        │
                                        ├── LangGraph workflow ──► OpenAI
                                        ├── PostgreSQL (disputes, transactions, audit log)
                                        └── OpenSearch (full-text search over disputes)
```

### Agent workflow

```
privacy_guard ─► intake ─► investigator ─┬─► fraud_agent  ─┬─► decision ─► router ─► END
                                         └─► policy_agent ─┘
                                            (run in parallel)
```

| Agent | What it does | Technique |
|---|---|---|
| **Privacy guard** | Masks card numbers, IBANs, emails, phone numbers and the customer's name before any LLM call | Regex + known names (no LLM) |

| Agent | What it does | Technique |
|---|---|---|
| **Intake** | Classifies the complaint (duplicate charge, unauthorized, subscription…) | Structured output (Pydantic) |
| **Investigator** | Decides which tools to call: transaction lookup, customer history, duplicate finder, merchant history | LLM tool calling, loop limit |
| **Fraud** | Combines deterministic rules (amount vs average, foreign country, night-time, new merchant) with LLM judgement | Hybrid rules + LLM |
| **Policy** | Retrieves only the policy rules relevant to the category and checks eligibility, citing rule IDs | Retrieval + structured output |
| **Decision** | Proposes refund / reject / escalate, with a rationale and a customer message | Structured output |
| **Router** | Sends the case to a human if fraud ≥ 70, amount ≥ 1000 EUR, low confidence or escalation | Plain code (no LLM) |

### Security & compliance
| Control | How it works |
|---|---|
| **Authentication** | `POST /auth/login` returns a JWT (HS256, 60 min). Passwords are stored as salted PBKDF2-SHA256 hashes (600,000 iterations) |
| **Roles** | `agent` submits disputes; only `reviewer` can approve or reject (`403` otherwise) |
| **Four-eyes principle** | A reviewer can never review a dispute they submitted themselves |
| **Identity from the token** | The reviewer's name is taken from the token, never from the request body, so nobody can act in someone else's name |
| **Account lockout** | 5 wrong passwords lock the account for 15 minutes; wrong user and wrong password give the same error |
| **Instant revocation** | The user is checked in the database on every request, so a deactivated employee loses access immediately |
| **PII masking** | The `privacy_guard` node masks personal data before any LLM call; tools return no names (data minimisation). The original text stays in our database; the customer's name is put back into the message only after the LLM is done |
| **Audit trail** | Who submitted, every agent step, and who reviewed (with the agent's suggestion and the human's decision) |
| **Security headers** | `nosniff`, `X-Frame-Options: DENY`, `no-store` caching on all responses |

Demo users (created on first start, password = `DEMO_PASSWORD`, default `Demo!2026`):
`arta` (agent), `ana` (reviewer), `leon` (reviewer).

### Analytics (`GET /analytics` and the Analytics tab)
Automation rate · human override rate (how often reviewers disagree with the agents) · disputes waiting for review ·
average fraud score · refunded amount · end-to-end workflow time · disputes by category · fraud risk distribution ·
average time per agent · disputes per day.

### Production concerns covered
- **Human in the loop:** risky cases wait for a reviewer (`POST /disputes/{id}/review`).
- **Reliability:** LLM outputs are validated with Pydantic, tool loops have a hard limit, and failures are logged and mark the dispute `failed`.
- **Testing:** 19 pytest tests with a fake LLM (auth, roles, four-eyes, lockout, PII never reaching the LLM, analytics), so everything is tested offline and for free.

## Run locally

### Option A: Docker Compose (Postgres + OpenSearch + backend + frontend)
```bash
export OPENAI_API_KEY=sk-...
docker compose up --build
```
Open http://localhost:5173. API docs: http://localhost:8000/docs

### Option B: without Docker (SQLite, no OpenSearch)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export OPENAI_API_KEY=sk-...                        # Windows: set OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload

cd ../frontend
npm install
npm run dev
```

### Tests
```bash
cd backend
pytest -q
```

### Demo scenarios (seed data)
| Customer | Transaction | Scenario | Expected result |
|---|---|---|---|
| C001 Arben | T1002 Viva Fresh 23.40 | Charged twice | Auto refund |
| C002 Drita | T2001 ElectroWorld Lagos 1,450 | Unauthorized, abroad, at night | Human review |
| C003 Blerim | T3001 StreamPlus 12.99 | Charged after cancelling | Refund or ask for proof |

## Deploy to AWS (Lambda + API Gateway)

You need the AWS CLI configured (`aws configure`) and Docker. The examples use `eu-central-1`.

### 1. Database
Lambda cannot use SQLite, so you need PostgreSQL. The simplest options are a free serverless Postgres
(e.g. Neon or Supabase) or Amazon RDS. Copy the connection string:
`postgresql+psycopg2://user:password@host:5432/dbname`

### 2. Build and push the Docker image to ECR
```bash
REGION=eu-central-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO=dispute-assistant

aws ecr create-repository --repository-name $REPO --region $REGION
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT.dkr.ecr.$REGION.amazonaws.com

cd backend
docker build --platform linux/amd64 --provenance=false -f Dockerfile.lambda -t $REPO .
docker tag $REPO:latest $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
docker push $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
```

### 3. Create the Lambda function
```bash
aws iam create-role --role-name dispute-lambda-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam attach-role-policy --role-name dispute-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws lambda create-function --function-name dispute-assistant --region $REGION \
  --package-type Image \
  --code ImageUri=$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest \
  --role arn:aws:iam::$ACCOUNT:role/dispute-lambda-role \
  --timeout 60 --memory-size 1024 \
  --environment "Variables={DATABASE_URL=postgresql+psycopg2://...,OPENAI_API_KEY=sk-...,JWT_SECRET=a-long-random-string,DEMO_PASSWORD=choose-one,CORS_ORIGINS=*}"
```
(For a real system, store secrets in AWS Secrets Manager instead of plain environment variables.)

### 4. Expose it with API Gateway (HTTP API)
```bash
LAMBDA_ARN=$(aws lambda get-function --function-name dispute-assistant --query Configuration.FunctionArn --output text)
aws apigatewayv2 create-api --name dispute-api --protocol-type HTTP --target $LAMBDA_ARN --region $REGION

aws lambda add-permission --function-name dispute-assistant --statement-id apigw \
  --action lambda:InvokeFunction --principal apigateway.amazonaws.com
```
The `create-api` output contains `ApiEndpoint`. Test it with `curl <ApiEndpoint>/health`.

### 5. Point the frontend at it
```bash
cd frontend
VITE_API_URL=<ApiEndpoint> VITE_API_KEY=choose-a-secret npm run build
```
Host the `dist/` folder anywhere static (S3 static website, Netlify, Vercel).
Note: a key built into frontend code is visible to anyone, so this is fine for a demo. In production you would use a
proper login (e.g. Amazon Cognito + an API Gateway JWT authorizer).

### Updating after code changes
```bash
docker build --platform linux/amd64 --provenance=false -f Dockerfile.lambda -t $REPO . && docker tag ... && docker push ...
aws lambda update-function-code --function-name dispute-assistant --image-uri $ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest
```

## Design notes / trade-offs (good interview talking points)
- **Why LangGraph instead of one big prompt?** Each agent has one job, its own prompt and a validated output. That
  makes steps testable, auditable and replaceable. Fraud and policy checks are independent, so they run in parallel.
- **Why rules plus an LLM for fraud?** Rules are explainable and deterministic, and the LLM adds context (e.g. "duplicate
  charge is a merchant error, not fraud"). The final score blends both.
- **Why is the router plain code?** Business-critical thresholds must be predictable and controlled by the bank, not by a model.
- **Synchronous processing:** API Gateway HTTP APIs time out after 30 s. The workflow makes ~5 LLM calls (about 5–15 s with
  gpt-4o-mini), so it fits. For heavier workloads: return `202 Accepted`, push the dispute ID to **SQS**, and process it in
  a second Lambda.
- **OpenSearch is optional:** without `OPENSEARCH_URL`, search falls back to SQL `ILIKE`, so the app also runs cheaply.

## Possible next steps
- Async processing with SQS + a worker Lambda
- Single sign-on (Amazon Cognito / company login) instead of local passwords
- Database migrations with Alembic
- LangGraph `interrupt()` + checkpointer for resumable human-in-the-loop
- Infrastructure as Code (Terraform or AWS SAM) for the AWS setup
- CloudWatch dashboard: dispute volume, auto-resolution rate, agent latency