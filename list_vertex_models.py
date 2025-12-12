import vertexai
from vertexai.preview.generative_models import GenerativeModel

# Initialize
vertexai.init(project="gen-lang-client-0650358146", location="us-central1")

# Try to list available models
try:
    from google.cloud import aiplatform
    aiplatform.init(project="gen-lang-client-0650358146", location="us-central1")
    
    print("Listing available models in us-central1...")
    models = aiplatform.Model.list(location="us-central1")
    for model in models:
        print(f"  - {model.name}")
        if 'deepseek' in model.name.lower():
            print(f"    [DEEPSEEK FOUND]")
except Exception as e:
    print(f"Error listing models: {e}")
    print("\nTrying alternate method...")
    
    # Try with prediction client
    try:
        from google.cloud.aiplatform_v1 import PredictionServiceClient
        client = PredictionServiceClient()
        print("Available via prediction service")
    except Exception as e2:
        print(f"Also failed: {e2}")
