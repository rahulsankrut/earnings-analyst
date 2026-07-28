import os
import sys
from google.cloud import aiplatform_v1
from google.api_core.client_options import ClientOptions
from google.protobuf import field_mask_pb2
from dotenv import load_dotenv

def patch():
    load_dotenv()

    resource_name = os.environ.get("REASONING_ENGINE_RESOURCE")
    if not resource_name:
        print("Error: Set REASONING_ENGINE_RESOURCE env var (e.g., projects/123/locations/us-central1/reasoningEngines/456)")
        sys.exit(1)

    location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    client_options = ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")
    client = aiplatform_v1.ReasoningEngineServiceClient(client_options=client_options)

    engine = client.get_reasoning_engine(name=resource_name)
    new_labels = dict(engine.labels) if engine.labels else {}
    new_labels["customer"] = os.environ.get("CUSTOMER_LABEL", "trane")
    engine.labels = new_labels

    update_mask = field_mask_pb2.FieldMask(paths=["labels"])
    request = aiplatform_v1.UpdateReasoningEngineRequest(
        reasoning_engine=engine,
        update_mask=update_mask
    )

    lro = client.update_reasoning_engine(request=request)
    lro.result()
    print(f"Label patched: customer={new_labels['customer']}")

if __name__ == "__main__":
    patch()
