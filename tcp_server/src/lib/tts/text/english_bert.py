import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM
import sys

from lib.constants import TTS_BERT_BASE_MODEL_DIR_PATH

load_model_params = {
    "pretrained_model_name_or_path": TTS_BERT_BASE_MODEL_DIR_PATH,
    "local_files_only": True
}
tokenizer = AutoTokenizer.from_pretrained(**load_model_params)
model = None

def get_bert_feature(text, word2ph, device=None):
    global model
    if (
        sys.platform == "darwin"
        and torch.backends.mps.is_available()
        and device == "cpu"
    ):
        device = "mps"
    if not device:
        device = "cuda"
    if model is None:
        model = AutoModelForMaskedLM.from_pretrained(**load_model_params).to(
            device
        )
    with torch.no_grad():
        inputs = tokenizer(text, return_tensors="pt")
        for i in inputs:
            inputs[i] = inputs[i].to(device)
        res = model(**inputs, output_hidden_states=True)
        res = torch.cat(res["hidden_states"][-3:-2], -1)[0].cpu()
        
    assert inputs["input_ids"].shape[-1] == len(word2ph)
    word2phone = word2ph
    phone_level_feature = []
    for i in range(len(word2phone)):
        repeat_feature = res[i].repeat(word2phone[i], 1)
        phone_level_feature.append(repeat_feature)

    phone_level_feature = torch.cat(phone_level_feature, dim=0)

    return phone_level_feature.T
