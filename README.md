# StateScout AI

StateScout AI is a policy-aware UI auditing engine that autonomously explores web applications and detects forbidden or logically invalid interface states.

It shifts automation from workflow testing to logical state verification.

---

## 🚩 The Problem

Modern web applications rely on backend Role-Based Access Control (RBAC) to protect sensitive actions.

However, frontend logic errors can still expose restricted interface components, such as:

- Admin dashboards visible to non-admin users
- Debug panels exposed in production
- Role-based rendering inconsistencies
- Unintended state transitions

Even if backend APIs block execution, UI exposure itself can violate access policies or compliance rules.

StateScout is designed to detect such logical UI exposure automatically.

---

## 🧠 Core Idea

Instead of validating predefined test scripts, StateScout:

1. Explores the interface autonomously  
2. Constructs a directed state graph of navigation paths  
3. Extracts semantic information from UI states  
4. Applies negation-aware policy evaluation  
5. Flags forbidden or logically invalid UI states  

It focuses on *what should NOT exist* rather than simply verifying expected workflows.

---

## 🏗 System Architecture

StateScout is structured into five logical layers:

### 1️⃣ Orchestration & Control
- Session lifecycle management
- Scan → Act → Observe loop
- Policy injection
- Exploration termination logic

### 2️⃣ Browser Interaction
- Playwright-based UI navigation
- DOM extraction
- Accessibility tree parsing
- Screenshot capture

### 3️⃣ Perception & Reasoning
- Vision-language model (inference only)
- UI semantic interpretation
- Policy-aware evaluation
- Negation-based violation detection

### 4️⃣ State & Graph Management
- UI state fingerprinting
- Directed navigation graph construction
- Loop prevention via visited state–action tracking
- State consistency validation

### 5️⃣ Persistence & Reporting
- Graph-based state storage
- Session tracking
- Structured violation reporting

---

## 🔎 What Makes It Different?

Traditional testing tools:
- Validate predefined workflows.

GUI agents:
- Focus on completing tasks.

StateScout:
- Audits logical UI exposure.
- Detects forbidden interface states.
- Verifies state-space consistency across navigation paths.

It reframes UI testing as a state-space auditing problem.

---

## 🛠 Tech Stack

- Python
- FastAPI
- Playwright
- Neo4j
- Multimodal Vision-Language Models (Inference-only)

---

## 📈 Project Status

StateScout AI is under active development as an 8-month strategic software project.

Current focus areas:
- Autonomous UI exploration
- State graph construction
- Policy-aware negation evaluation
- End-to-end violation reporting

---

## 👥 Team

Team 46  
Department of Computer Science & Engineering  
Amrita Vishwa Vidyapeetham

---

## 📜 License

To be added.
