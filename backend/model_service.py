import re
from typing import Optional

class ModelService:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.base_model = "Qwen/Qwen2.5-1.5B-Instruct"
        self.adapter = "D3v1k4/qwen-nlp-text-to-sql"

    @property
    def loaded(self):
        return self.model is not None and self.tokenizer is not None

    def attach(self, model, tokenizer):
        self.model = model
        self.tokenizer = tokenizer

    def generate(self, question: str, schema: dict) -> str:
        if not self.loaded:
            raise RuntimeError("Model is not attached. Load Qwen + LoRA and call pipeline.model.attach(model, tokenizer).")
        schema_text = []
        for table in schema.get("tables", []):
            cols = ", ".join(f'{c["name"]} {c["type"]}' for c in table.get("columns", []))
            schema_text.append(f'TABLE {table["name"]} ({cols})')
        prompt = (
            "You are a Text-to-SQL system. Convert the user's natural-language question into SQLite SQL.\n"
            "Return ONLY the SQL query, with no explanation, markdown, or code fences.\n\n"
            "Database schema:\n" + "\n".join(schema_text) +
            f"\n\nQuestion: {question}\nSQL:"
        )
        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer(text, return_tensors="pt")
        device = next(self.model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        output = self.model.generate(**inputs, max_new_tokens=256, do_sample=False, temperature=0.0)
        generated = self.tokenizer.decode(output[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        generated = re.sub(r"^```(?:sql)?\s*|\s*```$", "", generated, flags=re.I | re.S).strip()
        match = re.search(r"(?is)\b(?:WITH|SELECT)\b.*", generated)
        if not match:
            raise ValueError(f"Model did not return SQL: {generated}")
        sql = match.group(0).strip()
        return sql.split("```", 1)[0].strip()
