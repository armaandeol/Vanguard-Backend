# DeployIQ Backend

DeployIQ is an AI-powered pull request risk analysis backend. It predicts deployment risk for GitHub pull requests using machine learning, retrieval-augmented generation (RAG), and LLM-powered explanations. The backend helps engineering teams identify risky code changes before deployment by combining pull request metadata, repository knowledge, and predictive models.

---

## Features

### Pull Request Risk Detection

* Analyze GitHub pull requests automatically.
* Extract commit metadata, file changes, patch diffs, authors, branches, and repository context.
* Detect risky code changes before deployment.

### Machine Learning Risk Scoring

* XGBoost-based deployment risk prediction.
* Probability calibration for reliable confidence scores.
* Feature engineering from repository activity.
* Explainable risk metrics.

### Retrieval-Augmented Generation

* Repository-aware knowledge retrieval.
* Documentation and historical context ingestion.
* Semantic search over project knowledge.
* LLM-generated deployment risk explanations.

### FastAPI Backend

* RESTful API architecture.
* Modular routers.
* Authentication support.
* GitHub integration.
* Repository management APIs.

### Automated Knowledge Pipeline

* Startup ingestion pipeline.
* Automatic knowledge base initialization.
* Background indexing.
* Persistent vector knowledge storage.

---

## Architecture

```text
GitHub Pull Request
        |
        v
FastAPI API layer
        |
        v
GitHub client + PR detector
        |
        +--> Pull request metadata
        +--> Commit and file-change features
        +--> Repository context
        |
        v
Risk pipeline
        |
        +--> Feature engineering
        +--> XGBoost risk prediction
        +--> Probability calibration
        +--> Risk score from 0 to 100
        |
        v
RAG knowledge retrieval
        |
        v
LLM-generated risk explanation
        |
        v
Structured FastAPI response
```

The backend receives repository and pull request data through FastAPI, enriches it with GitHub metadata, scores deployment risk with the ML pipeline, retrieves relevant repository knowledge through RAG, and returns a structured response with both a numeric risk score and contextual explanation.

---

## Project Structure

```text
DeployIQ-backend/
|-- main.py                     # FastAPI application entrypoint
|-- requirements.txt            # Python dependencies
|-- .env.example                # Environment variable template
|-- app/
|   |-- auth.py                 # Authentication helpers
|   |-- config.py               # Environment and app configuration
|   |-- firebase.py             # Firebase/Firestore setup
|   |-- pr_detector.py          # Pull request feature extraction
|   |-- risk_pipeline.py        # End-to-end risk scoring and explanation flow
|   |-- schemas.py              # Shared Pydantic schemas
|   |-- utils.py                # Shared utility helpers
|   |-- github/
|   |   |-- auth.py             # GitHub App authentication
|   |   `-- client.py           # GitHub API client
|   |-- routers/
|   |   |-- github.py           # GitHub integration endpoints
|   |   |-- repos.py            # Repository endpoints
|   |   `-- users.py            # User endpoints
|   |-- RAG/
|   |   |-- agent.py            # RAG agent orchestration
|   |   |-- ingest.py           # Knowledge ingestion
|   |   |-- schemas.py          # RAG-specific schemas
|   |   |-- tools.py            # Retrieval and LLM tools
|   |   `-- knowledge_base/     # Local vector/knowledge artifacts
|   `-- HPE-Model/
|       |-- app.py              # Model serving/helpers
|       |-- model_card.md       # Model documentation
|       |-- models/             # Trained model artifacts
|       |-- apachejit_total.csv # Dataset snapshot
|       `-- README.md           # Model-specific notes
`-- tests/
    `-- test_risk_pipeline.py   # Risk pipeline tests
```

---

## Risk Prediction Pipeline

1. Fetch pull request metadata from GitHub.
2. Extract repository, commit, and code-change features.
3. Generate engineered ML features.
4. Predict deployment risk using the trained XGBoost model.
5. Calibrate prediction confidence.
6. Retrieve repository knowledge using RAG.
7. Generate contextual explanations with the LLM.
8. Return structured deployment insights through the API.

---

## Technology Stack

| Category | Technologies |
| --- | --- |
| Backend | FastAPI, Uvicorn |
| Language | Python |
| Machine Learning | XGBoost, Scikit-learn |
| AI | LLM, Retrieval-Augmented Generation (RAG) |
| GitHub Integration | GitHub REST API |
| Data Processing | Pandas, NumPy |
| Validation | Pydantic |
| Testing | Pytest |

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/DeployIQ.git
cd DeployIQ/DeployIQ-backend
```

If you already have the repository locally, run the remaining commands from `DeployIQ-backend/`.

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on macOS or Linux:

```bash
source .venv/bin/activate
```

Activate it on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Update `.env` with the credentials needed by your local setup:

| Variable | Purpose |
| --- | --- |
| `FIREBASE_SERVICE_ACCOUNT_FILE` | Path to the Firebase service account JSON file. |
| `FIRESTORE_DATABASE_ID` | Firestore database ID. |
| `GITHUB_APP_ID` | GitHub App ID. |
| `GITHUB_CLIENT_ID` | GitHub OAuth client ID. |
| `GITHUB_PRIVATE_KEY_PATH` | Path to the GitHub App private key. |
| `GITHUB_WEBHOOK_SECRET` | Secret used to validate GitHub webhooks. |
| `GITHUB_APP_SLUG` | GitHub App slug. |
| `FRONTEND_URL` | Frontend origin allowed by CORS. |
| `GITHUB_TOKEN` | GitHub token for API access when needed. |
| `GEMINI_API_KEY` | Gemini API key for LLM features. |
| `GROQ_API_KEY` | Groq API key for LLM features. |

### 5. Run the backend server

```bash
python main.py
```

You can also run it directly with Uvicorn:

```bash
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

Interactive API documentation is available at `http://localhost:8000/docs`.

---

## Running Tests

```bash
pytest
```

---

## Machine Learning Model

The repository contains a deployment risk prediction model.

Model artifacts include:

* XGBoost model.
* Probability calibrator.
* Feature schema.
* Evaluation metrics.
* Model card.
* Training notebook.
* Dataset snapshot.

The model predicts deployment risk using engineered features extracted from GitHub pull requests and historical repository activity.

---

## Retrieval-Augmented Generation

DeployIQ uses a RAG pipeline to provide repository-aware insights.

Capabilities include:

* Documentation ingestion.
* Knowledge indexing.
* Semantic retrieval.
* Context-aware reasoning.
* LLM-powered explanations.

The knowledge base is automatically initialized during application startup.

---

## API Overview

The FastAPI backend exposes endpoints for:

* GitHub repository management.
* Pull request analysis.
* User management.
* Repository information.
* Risk prediction.
* AI-powered deployment insights.

Interactive documentation is available through Swagger UI after starting the server.

---

## Future Improvements

* GitHub webhook integration.
* Real-time deployment monitoring.
* Kubernetes deployment support.
* CI/CD pipeline integration.
* Multi-repository analytics.
* Dashboard and visualization.
* Model retraining pipeline.
* Explainable AI dashboard.

---

## Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.

```bash
git checkout -b feature/my-feature
```

3. Commit your changes.

```bash
git commit -m "Add new feature"
```

4. Push your branch.

```bash
git push origin feature/my-feature
```

5. Open a pull request.

---

## License

This project currently does not include a license. Add an appropriate `LICENSE` file if you intend to distribute or open-source the project.

---

## Authors

Developed as part of DeployIQ, an AI-powered deployment intelligence platform that combines machine learning, GitHub analytics, retrieval-augmented generation, and large language models to improve deployment reliability.
