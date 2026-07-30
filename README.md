🚀 VanGuard - AI-Powered Pull Request Risk Analysis Platform

VanGuard is an intelligent DevOps platform that predicts deployment risk for GitHub Pull Requests using Machine Learning, Retrieval-Augmented Generation (RAG), and LLM-powered analysis. It helps engineering teams identify high-risk code changes before deployment by combining historical commit intelligence, repository knowledge, and predictive models.

⸻

✨ Features

🔍 Pull Request Risk Detection

* Analyze GitHub Pull Requests automatically
* Extract commit metadata, file changes, patch diffs, authors, branches, and repository context
* Detect risky code changes before deployment

🤖 Machine Learning Risk Scoring

* XGBoost-based deployment risk prediction
* Probability calibration for reliable confidence scores
* Feature engineering from repository activity
* Explainable risk metrics

📚 Retrieval-Augmented Generation (RAG)

* Repository-aware knowledge retrieval
* Documentation and historical context ingestion
* Intelligent retrieval for deployment reasoning
* Semantic search over project knowledge

⚡ FastAPI Backend

* RESTful API architecture
* Modular routing
* Authentication support
* GitHub integration
* Repository management APIs

🔄 Automated Knowledge Pipeline

* Startup ingestion pipeline
* Automatic knowledge base initialization
* Background indexing
* Persistent vector knowledge storage

⸻

🏗️ Architecture

                    GitHub Repository
                            │
                            ▼
                  Pull Request Detector
                            │
      ┌─────────────────────┴─────────────────────┐
      ▼                                           ▼
Feature Extraction                      Repository Metadata
      │                                           │
      └─────────────────────┬─────────────────────┘
                            ▼
                  Feature Engineering
                            │
                            ▼
               XGBoost Risk Prediction Model
                            │
                            ▼
                Probability Calibration
                            │
                            ▼
                    Risk Score (0-100)
                            │
                            ▼
                  RAG Knowledge Retrieval
                            │
                            ▼
                 LLM Risk Explanation
                            │
                            ▼
                  FastAPI REST Response

⸻

📂 Project Structure

VanGuard/
│
├── main.py                     # FastAPI application entrypoint
├── requirements.txt
├── .env.example
│
├── app/
│   ├── auth.py
│   ├── config.py
│   ├── firebase.py
│   ├── pr_detector.py          # PR feature extraction
│   ├── risk_pipeline.py        # End-to-end risk pipeline
│   ├── schemas.py
│   ├── utils.py
│   │
│   ├── github/
│   │   ├── auth.py
│   │   └── client.py
│   │
│   ├── routers/
│   │   ├── github.py
│   │   ├── repos.py
│   │   └── users.py
│   │
│   ├── RAG/
│   │   ├── agent.py
│   │   ├── ingest.py
│   │   ├── schemas.py
│   │   ├── tools.py
│   │   └── knowledge_base/
│   │
│   └── HPE-Model/
│       ├── app.py
│       ├── model_card.md
│       ├── models/
│       ├── apachejit_total.csv
│       └── README.md
│
└── tests/
    └── test_risk_pipeline.py

⸻

🧠 Risk Prediction Pipeline

1. Fetch Pull Request metadata from GitHub.
2. Extract repository, commit, and code-change features.
3. Generate engineered ML features.
4. Predict deployment risk using the trained XGBoost model.
5. Calibrate prediction confidence.
6. Retrieve repository knowledge using RAG.
7. Generate contextual explanations with the LLM.
8. Return structured deployment insights through the API.

⸻

🛠️ Technology Stack

Category	Technologies
Backend	FastAPI, Uvicorn
Language	Python
Machine Learning	XGBoost, Scikit-learn
AI	LLM, Retrieval-Augmented Generation (RAG)
GitHub Integration	GitHub REST API
Data Processing	Pandas, NumPy
Validation	Pydantic
Testing	Pytest

⸻

🚀 Getting Started

1. Clone the Repository

git clone https://github.com/<your-username>/VanGuard.git
cd VanGuard

⸻

2. Create a Virtual Environment

python -m venv .venv

macOS / Linux

source .venv/bin/activate

Windows

.venv\Scripts\activate

⸻

3. Install Dependencies

pip install -r requirements.txt

⸻

4. Configure Environment Variables

cp .env.example .env

Update the .env file with the required credentials.

⸻

5. Run the Server

python main.py

or

uvicorn main:app --reload

The API will be available at:

http://localhost:8000

Interactive API documentation:

http://localhost:8000/docs

⸻

🧪 Running Tests

pytest

⸻

🤖 Machine Learning Model

The repository contains a production-ready deployment risk prediction model.

Model artifacts include:

* XGBoost model
* Probability calibrator
* Feature schema
* Evaluation metrics
* Model card
* Training notebook
* Dataset snapshot

The model predicts deployment risk using engineered features extracted from GitHub Pull Requests and historical repository activity.

⸻

📚 Retrieval-Augmented Generation

VanGuard uses a Retrieval-Augmented Generation (RAG) pipeline to provide repository-aware insights.

Capabilities include:

* Documentation ingestion
* Knowledge indexing
* Semantic retrieval
* Context-aware reasoning
* LLM-powered explanations

The knowledge base is automatically initialized during application startup.

⸻

🔌 API Overview

The FastAPI backend exposes endpoints for:

* GitHub repository management
* Pull Request analysis
* User management
* Repository information
* Risk prediction
* AI-powered deployment insights

Interactive documentation is available through Swagger UI after starting the server.

⸻

📈 Future Improvements

* GitHub Webhook Integration
* Real-time Deployment Monitoring
* Kubernetes Deployment Support
* CI/CD Pipeline Integration
* Multi-Repository Analytics
* Dashboard & Visualization
* Model Retraining Pipeline
* Explainable AI Dashboard

⸻

🤝 Contributing

Contributions are welcome.

1. Fork the repository.
2. Create a feature branch.

git checkout -b feature/my-feature

3. Commit your changes.

git commit -m "Add new feature"

4. Push your branch.

git push origin feature/my-feature

5. Open a Pull Request.

⸻

📄 License

This project currently does not include a license. Add an appropriate LICENSE file if you intend to distribute or open-source the project.

⸻

👨‍💻 Authors

Developed as part of VanGuard, an AI-powered deployment intelligence platform that combines Machine Learning, GitHub analytics, Retrieval-Augmented Generation, and Large Language Models to improve deployment reliability.