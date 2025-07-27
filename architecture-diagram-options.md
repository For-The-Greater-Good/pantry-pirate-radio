# Architecture Diagram Options for Pantry Pirate Radio

## Option 1: Current Top-Down Flow with Custom Theme
```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#1976d2', 'primaryTextColor':'#fff', 'primaryBorderColor':'#0d47a1', 'lineColor':'#424242', 'secondaryColor':'#ff6f00', 'tertiaryColor':'#4a148c', 'background':'#fafafa', 'mainBkg':'#e3f2fd', 'secondBkg':'#fff3e0', 'tertiaryBkg':'#f3e5f5'}}}%%
flowchart TB
    %% Data Collection Layer
    Scrapers[Scrapers<br/>12+ sources] --> |submits jobs| RedisQueue[Redis Queue<br/>Job Queue]
    
    %% Content Store checks happen during job submission
    Scrapers --> |checks dedup| ContentStore[Content Store<br/>Deduplication]
    ContentStore --> |if new content| RedisQueue
    ContentStore --> |if duplicate| SkipLLM[Skip LLM<br/>Return existing job]
    
    %% LLM Processing Layer
    RedisQueue --> LLMWorkers[LLM Workers<br/>Scalable]
    LLMWorkers --> LLM[LLM Providers<br/>OpenAI/Claude]
    LLM --> |HSDS aligned data| LLMWorkers
    
    %% LLM Workers create new jobs
    LLMWorkers --> |creates reconciler job| ReconcilerQueue[Reconciler Jobs]
    LLMWorkers --> |creates recorder job| RecorderQueue[Recorder Jobs]
    
    %% Update Content Store after processing
    LLMWorkers --> |marks complete| ContentStore
    
    %% Reconciler Processing
    ReconcilerQueue --> Reconciler[Reconciler Service<br/>• Location matching<br/>• Entity deduplication<br/>• Version tracking]
    
    %% Recorder Processing
    RecorderQueue --> Recorder[Recorder Service<br/>• Archive JSON data]
    
    %% Storage Layer
    Reconciler --> PostgreSQL[(PostgreSQL +<br/>PostGIS<br/>HSDS Database)]
    Recorder --> OutputsFolder[outputs/<br/>JSON Files]
    
    %% API Layer
    PostgreSQL --> FastAPI[FastAPI<br/>Server]
    
    %% Publishing Layer
    OutputsFolder --> |reads JSON files| Publisher[HAARRRvest Publisher<br/>• Builds location map data<br/>• Exports DB to SQLite<br/>• Syncs content store]
    PostgreSQL --> |exports to SQLite| Publisher
    ContentStore -.-> |syncs for backup| Publisher
    
    Publisher --> HAARRRvest[HAARRRvest<br/>Repository]
    
    %% Style
    classDef service fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef storage fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef external fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef queue fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    
    class Scrapers,LLMWorkers,Reconciler,Recorder,FastAPI,Publisher service
    class ContentStore,PostgreSQL,OutputsFolder storage
    class LLM,HAARRRvest external
    class RedisQueue,ReconcilerQueue,RecorderQueue,SkipLLM queue
```

## Option 2: Left-to-Right Flow
```mermaid
flowchart LR
    %% Input
    Scrapers[Scrapers<br/>12+ sources] --> ContentStore{Content Store<br/>Dedup Check}
    
    %% Deduplication Decision
    ContentStore -->|New| Queue[Redis Queue]
    ContentStore -->|Duplicate| Skip[Return Existing]
    
    %% Processing
    Queue --> Workers[LLM Workers]
    Workers --> LLM[LLM Providers]
    LLM --> Workers
    
    %% Job Creation
    Workers --> RecJob[Reconciler Jobs]
    Workers --> RecordJob[Recorder Jobs]
    
    %% Services
    RecJob --> Reconciler[Reconciler<br/>Service]
    RecordJob --> Recorder[Recorder<br/>Service]
    
    %% Storage
    Reconciler --> DB[(PostgreSQL)]
    Recorder --> JSON[JSON Files]
    
    %% Output
    DB --> API[FastAPI]
    JSON --> Publisher[HAARRRvest<br/>Publisher]
    DB --> Publisher
    Publisher --> Repo[HAARRRvest<br/>Repo]
    
    %% Update tracking
    Workers -.-> |complete| ContentStore
    
    %% Styling
    classDef service fill:#bbdefb,stroke:#1565c0
    classDef storage fill:#ffe0b2,stroke:#ef6c00
    classDef external fill:#e1bee7,stroke:#6a1b9a
    
    class Scrapers,Workers,Reconciler,Recorder,API,Publisher service
    class ContentStore,DB,JSON storage
    class LLM,Repo external
```

## Option 3: With Subgraphs for Clarity
```mermaid
flowchart TB
    subgraph Input["📥 Data Collection"]
        Scrapers[Scrapers<br/>12+ sources]
        ContentStore{Content Store<br/>Deduplication}
        Scrapers --> ContentStore
    end
    
    subgraph Processing["⚙️ Processing Pipeline"]
        Queue[Redis Queue]
        Workers[LLM Workers]
        LLM[LLM Providers]
        ContentStore -->|New| Queue
        ContentStore -->|Duplicate| Skip[Skip Processing]
        Queue --> Workers
        Workers <--> LLM
    end
    
    subgraph Services["🔧 Service Layer"]
        ReconcilerQ[Reconciler Queue]
        RecorderQ[Recorder Queue]
        Reconciler[Reconciler Service]
        Recorder[Recorder Service]
        Workers --> ReconcilerQ
        Workers --> RecorderQ
        ReconcilerQ --> Reconciler
        RecorderQ --> Recorder
    end
    
    subgraph Storage["💾 Storage Layer"]
        DB[(PostgreSQL +<br/>PostGIS)]
        JSON[outputs/<br/>JSON Files]
        Reconciler --> DB
        Recorder --> JSON
    end
    
    subgraph Output["📤 Data Access"]
        API[FastAPI Server]
        Publisher[HAARRRvest Publisher]
        Repo[HAARRRvest Repository]
        DB --> API
        DB --> Publisher
        JSON --> Publisher
        Publisher --> Repo
    end
    
    Workers -.-> |marks complete| ContentStore
    ContentStore -.-> |backup| Publisher
```

## Option 4: Simplified Overview
```mermaid
graph TD
    Scrapers[🕷️ Scrapers] --> Dedup{Deduplication}
    Dedup -->|New| Process[🤖 LLM Processing]
    Dedup -->|Exists| Done[✅ Return Result]
    
    Process --> Match[🔍 Location Matching]
    Process --> Save[💾 Save JSON]
    
    Match --> DB[(🗄️ Database)]
    Save --> Files[📁 JSON Files]
    
    DB --> API[🌐 API]
    Files --> Publish[📤 Publish]
    DB --> Publish
    
    Publish --> Github[📚 GitHub Repository]
```

## Option 5: Dark Theme
```mermaid
%%{init: {'theme':'dark'}}%%
flowchart TD
    Scrapers[Scrapers] --> Queue[Job Queue]
    Scrapers --> Store[Content Store]
    Store --> Queue
    Queue --> Workers[LLM Workers]
    Workers --> Reconciler[Reconciler]
    Workers --> Recorder[Recorder]
    Reconciler --> DB[(PostgreSQL)]
    Recorder --> JSON[JSON Files]
    DB --> API[FastAPI]
    JSON --> Publisher[Publisher]
    DB --> Publisher
    Publisher --> GitHub[HAARRRvest]
```

## Option 6: Process State Diagram
```mermaid
stateDiagram-v2
    [*] --> Scraping: Start
    Scraping --> Deduplication: Content Retrieved
    
    state Deduplication {
        [*] --> CheckingHash
        CheckingHash --> NewContent: Not in Store
        CheckingHash --> Duplicate: Already Processed
    }
    
    Deduplication --> Queued: New Content
    Deduplication --> [*]: Duplicate Found
    
    Queued --> LLMProcessing: Worker Available
    
    state LLMProcessing {
        [*] --> SendingToLLM
        SendingToLLM --> ReceivingHSDS
        ReceivingHSDS --> CreatingJobs
    }
    
    LLMProcessing --> ReconcilerJob: Create Job
    LLMProcessing --> RecorderJob: Create Job
    
    ReconcilerJob --> LocationMatching
    RecorderJob --> SavingJSON
    
    LocationMatching --> DatabaseUpdated
    SavingJSON --> FileSaved
    
    DatabaseUpdated --> Publishing
    FileSaved --> Publishing
    
    Publishing --> [*]: Complete
```

## Option 7: Sequence Diagram for Job Flow
```mermaid
sequenceDiagram
    participant S as Scraper
    participant CS as Content Store
    participant Q as Redis Queue
    participant W as LLM Worker
    participant LLM as LLM Provider
    participant RQ as Reconciler Queue
    participant RecQ as Recorder Queue
    participant R as Reconciler
    participant Rec as Recorder
    participant DB as PostgreSQL
    participant FS as File System
    
    S->>CS: Check if content exists
    alt Content is new
        CS-->>S: Not found
        S->>Q: Submit job
        Q->>W: Get job
        W->>LLM: Process content
        LLM-->>W: HSDS data
        W->>CS: Mark complete
        W->>RQ: Create reconciler job
        W->>RecQ: Create recorder job
        RQ->>R: Process job
        RecQ->>Rec: Process job
        R->>DB: Update database
        Rec->>FS: Save JSON
    else Content exists
        CS-->>S: Return existing job ID
    end
```

## Recommendations

1. **For README**: Use Option 1 (current) or Option 3 (with subgraphs) for clarity
2. **For Architecture Docs**: Use Option 7 (sequence diagram) to show detailed flow
3. **For Presentations**: Use Option 4 (simplified overview) for non-technical audiences
4. **For Developer Docs**: Use Option 2 (left-to-right) as it follows reading direction

### Customization Tips
- Change `TB` to `LR` for horizontal layout
- Adjust colors in `themeVariables` to match your brand
- Use emoji in node labels for visual appeal
- Add `click NodeName "URL"` to make nodes clickable in supported viewers
- Use subgraphs to group related components