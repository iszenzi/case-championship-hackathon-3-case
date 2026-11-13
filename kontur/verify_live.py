"""Optional live Ollama smoke check. Uses temporary config, never changes your .env."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from server import App, ROOT
from llm import save_config


def main():
    with TemporaryDirectory() as temp:
        save_config(temp,{"provider":"ollama","base_url":"http://127.0.0.1:11434/v1","model":"mistral:latest","timeout":180,"max_tokens":1800})
        app=App(temp)
        c=app.dispatch('POST','/api/cases',{'scenario_id':'equipment'},{})
        c=app.dispatch('POST','/api/extract',{'id':c['id'],'revision':c['revision'],'mode':'llm'},{})
        response=app.dispatch('POST','/api/search',{'query':'Какие сведения нужно проверить для приема партии альтернативным терминалом?','mode':'llm'},{})
        result={"provider":"local Ollama","model":"mistral:latest","data_kind":"synthetic","extraction":c['facts'],"extraction_meta":c['extraction'],
                "knowledge_answer":response['answer'],"citation_ids":response['citation_ids'],"answer_meta":response['meta'],
                "note":"Two live calls verify integration only; not an accuracy benchmark or evidence of time savings."}
        out=ROOT/'qa';out.mkdir(exist_ok=True)
        (out/'live-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
