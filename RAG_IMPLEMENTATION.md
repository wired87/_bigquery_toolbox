# RAG Package Implementation & RELAY Notification System

## 📋 Overview

This implementation wraps all chat logic within a **RAG (Retrieval Augmented Generation) package** and exposes it globally for efficient access. It also implements a **real-time RELAY module notification system** that informs frontend users about dynamically discovered packages.

---

## 🏗️ Architecture

### 1. **RAG Package Structure**

```
rag/
├── __init__.py          # Package exports and global accessor
├── core.py              # RAG Core - Unified chat logic wrapper
└── global_registry.py   # Global singleton registry with RELAY notifications
```

### 2. **Component Breakdown**

#### **RAG Core (`rag/core.py`)**
- **Purpose**: Wraps all engine operations in a unified, efficient interface
- **Features**:
  - Request tracking and management
  - Automatic timeout handling
  - Context-aware processing
  - Statistics and monitoring
  
**Key Methods**:
```python
async def process(user_input, status_callback, context) -> Dict
async def authenticate(email, password) -> Dict
async def handle_file_upload(...) -> str
def get_stats() -> Dict
```

#### **Global Registry (`rag/global_registry.py`)**
- **Purpose**: Thread-safe singleton pattern for global RAG access
- **Features**:
  - Global instance management
  - RELAY package notification system
  - Listener registration and broadcasting
  - Discovery tracking

**Key Methods**:
```python
@classmethod initialize(rag_core) -> None
@classmethod get_instance() -> RAGCore
@classmethod register_relay_listener(callback) -> None
@classmethod notify_relay_discovered(relay_info) -> None
@classmethod get_discovered_relays() -> List[Dict]
```

---

## 🔌 RELAY Module Discovery System

### **How It Works**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Environment Scanner (validator.py)                       │
│    - Scans os.environ every 5 seconds                       │
│    - Looks for variables starting with "RELAY_"             │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Parse & Register (validator.py)                          │
│    - Parse JSON configuration                               │
│    - Create ToolCase                                        │
│    - Add to ARSENAL                                         │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Notify Global Registry (validator.py)                    │
│    - Create relay_info dict                                 │
│    - Call GlobalRAGRegistry.notify_relay_discovered()       │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Broadcast to Listeners (global_registry.py)              │
│    - Iterate through all registered callbacks               │
│    - Call each async listener with relay_info               │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Frontend Notification (consumers.py)                     │
│    - relay_notification_callback() receives update          │
│    - Sends WebSocket message to frontend                    │
│    - Type: "relay_module_discovered"                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📡 Frontend Integration

### **WebSocket Message Types**

#### 1. **Initial Connection** (sent on connect)
```json
{
  "type": "relay_modules_initial",
  "modules": [
    {
      "env_key": "RELAY_CUSTOM",
      "key": "custom_action",
      "description": "Custom functionality",
      "pattern": "custom|action",
      "priority": 50,
      "action": "do_custom",
      "timestamp": 1234567890.123
    }
  ],
  "count": 1
}
```

#### 2. **Real-time Discovery** (sent when new RELAY found)
```json
{
  "type": "relay_module_discovered",
  "module": {
    "env_key": "RELAY_NEW_FEATURE",
    "key": "new_feature",
    "description": "Newly discovered feature",
    "pattern": "feature|new",
    "priority": 75,
    "action": "execute_feature",
    "timestamp": 1234567890.456
  },
  "message": "🔌 New module available: Newly discovered feature"
}
```

---

## 🚀 Usage Examples

### **Backend: Accessing RAG Globally**

```python
from rag import get_rag_instance

# Get global instance
rag = get_rag_instance()

# Process a query
result = await rag.process(
    "Find documents about Python",
    status_callback=my_callback,
    context={'user_id': '123'}
)

# Get statistics
stats = rag.get_stats()
print(f"Active requests: {stats['active_requests']}")
```

### **Backend: Registering RELAY Listener**

```python
from rag.global_registry import GlobalRAGRegistry

async def my_relay_listener(relay_info: dict):
    print(f"New RELAY: {relay_info['key']}")
    # Send notification, log, etc.

GlobalRAGRegistry.register_relay_listener(my_relay_listener)
```

### **Setting RELAY Environment Variable**

```bash
# Windows
set RELAY_CUSTOM_EXPORT={"key":"export_data","description":"Export to CSV","pattern":"export|download","priority":85,"action":"export_csv"}

# Linux/Mac
export RELAY_CUSTOM_EXPORT='{"key":"export_data","description":"Export to CSV","pattern":"export|download","priority":85,"action":"export_csv"}'
```

### **Frontend: Handling RELAY Messages**

```javascript
const socket = new WebSocket('ws://localhost:8000/ws/chat/');

socket.onmessage = function(event) {
    const data = JSON.parse(event.data);
    
    // Initial modules on connect
    if (data.type === 'relay_modules_initial') {
        console.log(`Found ${data.count} RELAY modules:`, data.modules);
        displayModules(data.modules);
    }
    
    // Real-time discovery
    if (data.type === 'relay_module_discovered') {
        console.log('New module discovered:', data.module);
        showNotification(data.message);
        addModuleToUI(data.module);
    }
};
```

---

## 🔧 Configuration

### **RAG Configuration**

```python
from rag import RAGCore, RAGConfig

config = RAGConfig(
    timeout_classification=30.0,
    timeout_search=90.0,
    timeout_sql=120.0,
    timeout_chat=60.0,
    max_retry_attempts=2,
    enable_history_rewrite=True
)

rag = RAGCore(engine, config=config)
```

---

## 📊 Benefits

### **1. Efficiency Improvements**
- ✅ **Centralized Logic**: All chat operations in one place
- ✅ **Request Tracking**: Monitor active and completed requests
- ✅ **Timeout Management**: Automatic timeout handling per operation type
- ✅ **Resource Cleanup**: Automatic cleanup of old requests

### **2. Global Accessibility**
- ✅ **Singleton Pattern**: Single RAG instance accessible anywhere
- ✅ **Thread-Safe**: Protected by threading locks
- ✅ **No Import Complexity**: Simple `get_rag_instance()` call

### **3. Real-time RELAY Notifications**
- ✅ **Immediate Feedback**: Users notified as soon as modules are discovered
- ✅ **Concurrent Scanning**: Background thread doesn't block main operations
- ✅ **Persistent Discovery**: All discovered modules are tracked and sent to new connections

### **4. Scalability**
- ✅ **Isolated Concerns**: RAG, Engine, and Consumers are properly separated
- ✅ **Easy Testing**: Mock RAG Core independently
- ✅ **Future Extensibility**: Easy to add new features to RAG layer

---

## 🔍 Monitoring & Debugging

### **Get RAG Statistics**

```python
from rag import get_rag_instance

rag = get_rag_instance()
stats = rag.get_stats()

print(f"""
RAG Core Statistics:
- Active Requests: {stats['active_requests']}
- Total Processed: {stats['total_processed']}
- Authenticated: {stats['engine_authenticated']}
- Current User: {stats['current_user']}
""")
```

### **View Discovered RELAY Modules**

```python
from rag.global_registry import GlobalRAGRegistry

modules = GlobalRAGRegistry.get_discovered_relays()
for module in modules:
    print(f"- {module['key']}: {module['description']} (Priority: {module['priority']})")
```

---

## 🛠️ Technical Implementation Details

### **Thread Safety**
- Uses `threading.Lock()` for registry access
- Async event loop creation for RELAY notifications from sync thread
- Separate event loops prevent blocking

### **Memory Management**
- Active requests auto-cleanup after 5 minutes
- Discovered RELAY modules persist for session lifetime
- Listeners registered per WebSocket connection

### **Error Handling**
- Graceful fallback if RAG not initialized
- RELAY notification failures logged but don't crash scanner
- WebSocket disconnections handled cleanly

---

## 📝 Summary

This implementation provides:

1. **Unified RAG Package** - All chat logic centralized and efficient
2. **Global Registry** - Thread-safe singleton access throughout the application
3. **Real-time RELAY Notifications** - Concurrent scanning with instant frontend updates
4. **Comprehensive Statistics** - Monitor performance and usage
5. **Clean Architecture** - Proper separation of concerns

The system is production-ready, scalable, and provides excellent developer and user experience.
