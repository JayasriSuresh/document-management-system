import sys, os
sys.path.insert(0, os.path.abspath('backend'))
import torch
from transformers import AutoProcessor, AutoModelForCausalLM

device = "cuda" if torch.cuda.is_available() else "cpu"
torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
model_id = "microsoft/Florence-2-base"
print(f"Loading {model_id} on {device}...")

florence_model = AutoModelForCausalLM.from_pretrained(
    model_id, 
    torch_dtype=torch_dtype, 
    trust_remote_code=True
).to(device)
florence_processor = AutoProcessor.from_pretrained(
    model_id, 
    trust_remote_code=True
)
print("Florence-2 loaded successfully!")
