# AI Copilot - Cybersecurity Command Center

## Overview

AMMU AI is an advanced cybersecurity platform powered by Google Gemini API that combines AI-driven security analysis, red team operations, and comprehensive reporting. The system provides a command center interface for cybersecurity professionals, featuring AI-powered capabilities including secure code analysis, exploit generation, threat simulation, OSINT reconnaissance, and automated report generation.

The application serves as a comprehensive cybersecurity workspace with five specialized operational areas:
1. **Chat/RAG** - AI-powered conversations with document analysis
2. **Coding** - Security code review and exploit proof-of-concept generation  
3. **Red Team** - Attack simulations, phishing campaigns, and penetration testing workflows
4. **OSINT** - Open source intelligence gathering and reconnaissance
5. **Reports** - AI-generated security assessment reports with MITRE ATT&CK mapping

## Recent Changes (Migration Completed)

### AI Service Migration (December 2024)
- ✅ **Complete OpenAI to Gemini Migration**: Successfully migrated entire codebase from OpenAI API to Google Gemini API
- ✅ **New AIService Implementation**: Created comprehensive AIService class using Gemini 2.5 Flash/Pro models
- ✅ **RAG System Updated**: Updated document embeddings and retrieval to use Gemini embedding models
- ✅ **Emotional AI Enhanced**: Migrated emotional analysis and bonding system to Gemini-based processing

### Security Features Implementation
- ✅ **Advanced Coding Assistant**: Implemented comprehensive security code analysis with vulnerability detection and exploit PoC generation
- ✅ **Red Team Operations**: Built complete attack simulation framework with phishing campaigns and multi-step attack chains
- ✅ **OSINT Intelligence**: Developed domain reconnaissance, GitHub intelligence, and Shodan integration capabilities
- ✅ **Automated Reporting**: Created AI-powered security report generation with MITRE ATT&CK framework mapping
- ✅ **Educational Safety Measures**: Added appropriate warnings and disclaimers for all security testing features

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: React with TypeScript, built using Vite for development and bundling
- **Styling**: Tailwind CSS with custom cybersecurity theme colors (cyber-blue, cyber-green, cyber-amber, cyber-red)
- **UI Components**: Radix UI primitives with shadcn/ui components for consistent design system
- **State Management**: Zustand stores for chat, voice, and emotional state management
- **Routing**: Wouter for lightweight client-side routing
- **Data Fetching**: TanStack Query for server state management with custom API client

### Backend Architecture
- **Runtime**: Node.js with Express.js framework
- **Language**: TypeScript with ES modules
- **API Design**: RESTful endpoints with middleware-based authentication
- **File Processing**: Multer for file uploads with memory storage
- **Authentication**: JWT-based with bcrypt for password hashing
- **Session Management**: Express sessions with PostgreSQL store

### Data Storage Solutions
- **Primary Database**: PostgreSQL with Drizzle ORM for type-safe database operations
- **Connection**: Neon serverless PostgreSQL with connection pooling
- **Schema Design**: Comprehensive schema including users, documents, chunks (for RAG), sessions, messages, memories, tool runs, findings, and voice interactions
- **Vector Storage**: ChromaDB integration for RAG document embeddings and similarity search

### Authentication and Authorization
- **Strategy**: JWT token-based authentication with role-based access control
- **Roles**: Owner and Analyst roles with different permission levels
- **Session Management**: Persistent sessions stored in PostgreSQL
- **Middleware**: Custom authentication middleware for protected routes
- **Security**: Bcrypt password hashing with configurable rounds

### AI and ML Integration
- **Primary AI**: Google Gemini 2.5 Flash/Pro for chat completions and reasoning (migrated from OpenAI)
- **Embeddings**: Gemini text-embedding models for RAG vector storage
- **Voice Processing**: Gemini-based text analysis for emotional tone detection
- **Emotional AI**: Custom emotional bonding system with mood tracking and personality adaptation
- **Agent System**: Multi-step planning with approval workflows for high-risk operations
- **RAG System**: Document ingestion with text extraction, chunking, and vector embeddings

### Voice and Audio Processing
- **Wake Word Detection**: "Hey Ammu" wake word activation
- **Speech Recognition**: Web Speech API with fallback support
- **Audio Visualization**: Real-time audio level monitoring and waveform display
- **Voice Synthesis**: Text-to-speech with emotional tone adaptation
- **Audio Recording**: MediaRecorder API with configurable quality settings

### Security Tools Integration
- **Network Scanning**: Sandboxed Nmap wrappers with target restrictions
- **OSINT Tools**: Domain research, DNS lookups, subdomain enumeration
- **Vulnerability Research**: CVE database integration and exploit chain mapping
- **MITRE ATT&CK**: Technique mapping and attack chain visualization
- **Risk Assessment**: Multi-level risk evaluation (low/medium/high) for all operations

### Memory and Learning Systems
- **Episodic Memory**: Session-based conversation history with context preservation
- **Semantic Memory**: User preferences, learned facts, and domain knowledge
- **Procedural Memory**: Successful workflow patterns and automation templates
- **Emotional Memory**: Relationship building, trust development, and communication style adaptation

## External Dependencies

### Core AI Services
- **Google Gemini API**: Primary AI service using Gemini 2.5 Flash/Pro models for all completions
- **Gemini Embeddings**: Text embedding models for RAG document processing and similarity search

### Database and Storage
- **Neon PostgreSQL**: Serverless PostgreSQL database with connection pooling
- **ChromaDB**: Vector database for RAG document embeddings and similarity search

### Security and Networking
- **Nmap**: Network scanning tool (sandboxed execution for security)
- **DNS Resolution**: System DNS tools for OSINT operations
- **Certificate Analysis**: TLS/SSL certificate inspection tools

### Development and Build Tools
- **Vite**: Frontend build tool and development server
- **TypeScript**: Type system for both frontend and backend
- **Drizzle Kit**: Database migration and schema management
- **ESBuild**: Backend bundling for production deployment

### UI and Styling
- **Tailwind CSS**: Utility-first CSS framework
- **Radix UI**: Headless UI primitives for accessibility
- **Lucide React**: Icon system for consistent iconography
- **React Hook Form**: Form validation and management

### Audio and Media Processing
- **Web APIs**: MediaRecorder, Web Speech API, AudioContext for browser-based audio processing
- **File Processing**: PDF parsing, image OCR, text extraction from various document formats

### Authentication and Security
- **JSON Web Tokens (JWT)**: Token-based authentication
- **bcryptjs**: Password hashing and verification
- **Express Session**: Session management with PostgreSQL storage