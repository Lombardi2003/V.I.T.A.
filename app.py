import shutil, os

from src.graph import generate_graph
from src.state import MedicalState

# Main
if __name__ == "__main__":
    app = generate_graph()
    os.system('cls' if os.name == 'nt' else 'clear')
    terminal_width = shutil.get_terminal_size().columns
    titolo = "🩺 Virtual Intelligent Triage Assistant 🩺"
    print(titolo.center(terminal_width))

    app.invoke(MedicalState())

    titolo = "✅ PROCESSO COMPLETATO ✅"
    print(titolo.center(terminal_width))