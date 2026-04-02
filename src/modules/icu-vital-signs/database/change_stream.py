"""
change_stream.py – MongoDB Change Stream Trigger Simulation
Module 25: ICU Vital Signs Monitoring
"""
import threading

def watch_vital_signs(db, callback):
    """
    Simulates an Atlas Trigger using MongoDB Change Streams.
    Listens for new inserts where NEWS2 score >= 7.
    """
    pipeline = [
        {"$match": {"operationType": "insert", "fullDocument.news2_score": {"$gte": 7}}}
    ]
    
    def listen():
        try:
            with db.vital_signs.watch(pipeline) as stream:
                for change in stream:
                    doc = change.get("fullDocument")
                    if doc:
                        callback(doc)
        except Exception as e:
            print(f"Change stream error: {e}")
            
    # Run in background to avoid blocking API
    t = threading.Thread(target=listen, daemon=True)
    t.start()
    return t

def get_trigger_definition():
    """Returns the trigger pipeline for UI display."""
    return [
        {"$match": {"operationType": "insert", "fullDocument.news2_score": {"$gte": 7}}}
    ]
