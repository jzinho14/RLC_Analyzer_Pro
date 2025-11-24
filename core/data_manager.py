import pandas as pd
import os
import json
from datetime import datetime
from pathlib import Path

class DataManager:
    def __init__(self, project_folder_name="RLC_Analyzer_Projects"):

        user_documents = Path.home() / "Documents"
        self.save_dir = user_documents / project_folder_name
        
        # Garante que o diretório exista
        if not self.save_dir.exists():
            self.save_dir.mkdir(parents=True, exist_ok=True)
        
        self.save_dir = str(self.save_dir)

    def save_theoretical_params(self, name, parameters):
        """Salva parâmetros teóricos e tolerâncias para comparação futura."""
        exp_path = os.path.join(self.save_dir, name)
        if not os.path.exists(exp_path):
            os.makedirs(exp_path)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Salva apenas a metadata teórica
        parameters['timestamp'] = timestamp
        json_path = os.path.join(exp_path, f"{name}_theoretical_{timestamp}.json")
        with open(json_path, 'w') as f:
            json.dump(parameters, f, indent=4)
        
        return exp_path
    
    def load_theoretical_data(self, exp_name):
        """Carrega o último arquivo JSON teórico de um experimento."""
        exp_path = os.path.join(self.save_dir, exp_name)
        
        # Verifica se a pasta existe e lista arquivos
        if not os.path.exists(exp_path): return None, None
        
        files = os.listdir(exp_path)
        
        json_files = sorted([f for f in files if 'theoretical' in f.lower() and f.endswith('.json')], reverse=True)
        
        if not json_files:
            return None, None

        # Carrega metadata teórica (e os parâmetros para reconstruir a curva)
        json_path = os.path.join(exp_path, json_files[0])
        with open(json_path, 'r') as f:
            metadata = json.load(f)
            
        # Para fins de plotagem, o "dado" é apenas a metadata.
        # Retornamos None para o DF, pois a curva é reconstruída na aba de Análise
        return metadata, metadata

    def save_experiment(self, name, data_points, metadata):
        """Salva os dados brutos e metadata em uma pasta com o nome do experimento."""
        exp_path = os.path.join(self.save_dir, name)
        if not os.path.exists(exp_path):
            os.makedirs(exp_path)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Salva dados brutos (DataFrame)
        df = pd.DataFrame(data_points, columns=['Frequency', 'V_Resistor'])
        csv_path = os.path.join(exp_path, f"{name}_{timestamp}.csv")
        df.to_csv(csv_path, index=False)
        
        # Salva metadata (Componentes, Configurações, etc.)
        metadata['timestamp'] = timestamp
        metadata['file_path'] = csv_path
        json_path = os.path.join(exp_path, f"{name}_metadata.json")
        with open(json_path, 'w') as f:
            json.dump(metadata, f, indent=4)
        
        return exp_path

    def list_experiments(self):
        """Lista todos os experimentos salvos (nome das pastas)."""
        return [d for d in os.listdir(self.save_dir) if os.path.isdir(os.path.join(self.save_dir, d))]

    def load_experiment_data(self, exp_name):
        """Carrega o último arquivo CSV e o metadata de um experimento."""
        exp_path = os.path.join(self.save_dir, exp_name)
        
        # Encontra o último arquivo CSV e JSON
        files = os.listdir(exp_path)
        csv_files = sorted([f for f in files if f.endswith('.csv')], reverse=True)
        json_files = sorted([f for f in files if f.endswith('.json')], reverse=True)
        
        if not csv_files or not json_files:
            return None, None # Nenhum dado encontrado

        # Carrega dados
        csv_path = os.path.join(exp_path, csv_files[0])
        df = pd.read_csv(csv_path)

        # Carrega metadata
        json_path = os.path.join(exp_path, json_files[0])
        with open(json_path, 'r') as f:
            metadata = json.load(f)
            
        return df, metadata