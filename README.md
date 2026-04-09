# 🔐 Data Trust Ledger System

A blockchain-inspired backend system to track the complete, immutable provenance of datasets in a public sector data lake.

---

## 🚀 Features

- Immutable ledger using hash chaining
- Tracks Upload, Modify, and Access operations
- Dynamic Trust Score calculation
- REST APIs built with FastAPI
- MongoDB integration

---

## 🧠 Architecture

Frontend (UI Dashboard)
        ↓
FastAPI Backend (Ledger System)
        ↓
MongoDB Database

---

## ⚙️ Tech Stack

- Python
- FastAPI
- MongoDB
- Hashlib

---

## 📊 Trust Score Logic

- Source Reliability (0–40)
- Modification History (0–40)
- Access Pattern (0–20)

---

## ▶️ Run Locally

```bash
uvicorn main:app --reload
