# Mermaid Diagram Rendering Options

## 1. Different Graph Types

### Flowchart with Different Directions
- `graph TD` or `flowchart TD` - Top Down
- `graph LR` or `flowchart LR` - Left to Right  
- `graph BT` or `flowchart BT` - Bottom to Top
- `graph RL` or `flowchart RL` - Right to Left

### Other Diagram Types
- `sequenceDiagram` - For showing sequential flows
- `stateDiagram-v2` - For state machines
- `erDiagram` - For entity relationships
- `gitGraph` - For git workflows

## 2. Themes

### Built-in Themes
```mermaid
%%{init: {'theme':'default'}}%%
```
- `default` - Standard blue theme
- `neutral` - Gray theme
- `dark` - Dark mode theme
- `forest` - Green theme
- `base` - Customizable base theme

## 3. Custom Styling

### Using themeVariables
```mermaid
%%{init: {'theme':'base', 'themeVariables': {
  'primaryColor':'#ff0000',
  'primaryTextColor':'#fff',
  'primaryBorderColor':'#7C0000',
  'lineColor':'#000000',
  'secondaryColor':'#006100',
  'tertiaryColor':'#fff',
  'background':'#f4f4f4'
}}}%%
```

### Using CSS Classes
```mermaid
graph TD
    A[Service]:::serviceClass
    B[Storage]:::storageClass
    
    classDef serviceClass fill:#e1f5fe,stroke:#01579b,stroke-width:3px
    classDef storageClass fill:#fff3e0,stroke:#e65100,stroke-width:3px
```

## 4. Node Shapes

- `A[Rectangle]` - Default rectangle
- `A(Rounded Rectangle)` - Rounded corners
- `A{Diamond}` - Decision shape
- `A((Circle))` - Circle shape
- `A>Asymmetric]` - Tag shape
- `A{{Hexagon}}` - Hexagon shape
- `A[/Parallelogram/]` - Parallelogram
- `A[\Parallelogram\]` - Inverted parallelogram
- `A[/Trapezoid\]` - Trapezoid
- `A[\Trapezoid/]` - Inverted trapezoid
- `A(((Double Circle)))` - Double circle

## 5. Line Types

- `A --> B` - Solid arrow
- `A --- B` - Solid line
- `A -.-> B` - Dotted arrow
- `A -.- B` - Dotted line
- `A ==> B` - Thick arrow
- `A === B` - Thick line

## 6. Subgraphs

```mermaid
graph TD
    subgraph "Data Layer"
        A[Database]
        B[Cache]
    end
    
    subgraph "Service Layer"
        C[API]
        D[Workers]
    end
```

## Examples for Our Architecture

### Option 1: Left-to-Right Flow
```mermaid
flowchart LR
    Scrapers --> ContentStore
    ContentStore --> Queue
    Queue --> Workers
    Workers --> Services
```

### Option 2: With Subgraphs
```mermaid
flowchart TB
    subgraph Collection["Data Collection"]
        Scrapers[Scrapers]
        ContentStore[Content Store]
    end
    
    subgraph Processing["Processing"]
        Workers[LLM Workers]
        Reconciler[Reconciler]
    end
    
    subgraph Storage["Storage"]
        DB[(PostgreSQL)]
        Files[JSON Files]
    end
```

### Option 3: State Diagram
```mermaid
stateDiagram-v2
    [*] --> Scraping
    Scraping --> Deduplication
    Deduplication --> Queued: New Content
    Deduplication --> [*]: Duplicate
    Queued --> Processing
    Processing --> Recording
    Processing --> Reconciling
    Recording --> Published
    Reconciling --> Published
    Published --> [*]
```

### Option 4: Sequence Diagram
```mermaid
sequenceDiagram
    participant S as Scraper
    participant CS as Content Store
    participant Q as Queue
    participant W as Worker
    participant R as Reconciler
    
    S->>CS: Check dedup
    CS-->>S: New content
    S->>Q: Submit job
    Q->>W: Process job
    W->>R: Create reconciler job
```