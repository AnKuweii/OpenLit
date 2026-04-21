# OpenLit - Frontend

A modern document analysis interface built with React + TypeScript + Tailwind CSS.

## Quick Start

```bash
npm install
npm run dev
```

Dev server runs at `http://localhost:3000`.

## Production Build

```bash
npm run build
npm run start
```

## Configuration

### Backend API

Default backend: `http://localhost:8001/api/v1`

Create `.env.local` to override:

```bash
VITE_API_BASE_URL=http://localhost:8001/api/v1
```

Or edit `services/api.ts` directly.

## Tech Stack

- React 18 + TypeScript
- Tailwind CSS v4
- shadcn/ui components
- Lucide icons
- Sonner notifications

## Project Structure

```
├── App.tsx                 # Main application
├── components/             # React components
│   ├── ChatInterface.tsx   # Chat UI
│   ├── Header.tsx          # Top navigation
│   ├── HealthCheck.tsx     # API status
│   ├── MarkdownRenderer.tsx # Markdown renderer
│   ├── PDFPanel.tsx        # PDF viewer
│   └── ui/                 # Base UI components
├── services/
│   └── api.ts              # API layer
└── styles/
    └── globals.css         # Global styles & theme
```

## API Endpoints

```
GET  /api/v1/health
POST /api/v1/pdf/upload
POST /api/v1/pdf/parse
GET  /api/v1/pdf/status
GET  /api/v1/pdf/page
POST /api/v1/index/build
POST /api/v1/index/search
POST /api/v1/chat
GET  /api/v1/pdf/chunk
POST /api/v1/chat/clear
```
