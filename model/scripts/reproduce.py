"""Run all canonical calculations without downloading dependencies or changing inputs."""
from pathlib import Path
import subprocess,sys
R=Path(__file__).resolve().parents[1]
for name in ['build_dashboard.py','port_examples.py','audit_python_js.py']:
    subprocess.run([sys.executable,str(R/'scripts'/name)],cwd=R,check=True)
subprocess.run(['node',str(R/'scripts/export_scenarios.cjs')],cwd=R,check=True)
print('Reproduction complete. Compare results/ and app/index.html with Git.')
