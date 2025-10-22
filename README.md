# App Interno ASP Autopeças

## Visão Geral

Este é um aplicativo web interno desenvolvido em Flask (Python) para a ASP Autopeças. Ele serve como um painel central para comunicação e organização interna entre o dono e os funcionários. O aplicativo foi projetado para rodar localmente na rede da empresa.

## Funcionalidades Principais

* **Quadro de Avisos:** O administrador (Dono) pode postar comunicados importantes que são exibidos na página inicial para todos os funcionários logados.
* **Gerenciamento de Funcionários:** O admin pode cadastrar, visualizar e excluir funcionários, definindo seus dados básicos, setor (Escritório/Expedição) e informações de login.
* **Escala de Limpeza:** O admin pode definir uma escala de limpeza diária, designando um funcionário do Escritório e um da Expedição para a tarefa. A escala é visível para todos os funcionários.
* **Calendário Interativo:**
    * Exibe um calendário mensal navegável.
    * Destaca feriados cadastrados pelo admin.
    * Destaca automaticamente os aniversários dos funcionários cadastrados.
    * O admin pode cadastrar e excluir feriados.
* **Aniversariante do Dia:** A página inicial exibe um destaque especial parabenizando os funcionários que fazem aniversário no dia atual.
* **Sistema de Login:**
    * Todos os acessos exigem login (usuário e senha).
    * Controle de acesso baseado em papéis:
        * **Admin (Dono):** Acesso total, incluindo todas as funcionalidades de gerenciamento (`/admin/...`).
        * **User (Funcionário):** Acesso apenas às páginas de visualização (Avisos, Escala, Calendário).
* **Design Personalizado:** Tema claro com as cores da marca ASP Autopeças (branco, preto, vermelho) e fonte Orbitron.
* **Instalável (PWA):** Pode ser adicionado à tela inicial de celulares (Android/iOS) para acesso rápido, funcionando como um aplicativo.

## Tecnologias Utilizadas

* **Backend:** Python 3
* **Framework:** Flask
* **Banco de Dados:** SQLite
* **Autenticação:** Flask-Login
* **ORM:** Flask-SQLAlchemy
* **Frontend:** HTML, CSS (sem framework CSS externo)
* **Servidor de Desenvolvimento:** Werkzeug (embutido no Flask)

## Configuração e Execução Local

**Pré-requisitos:**
* Python 3 instalado
* Git (opcional, para clonar)

**Passos:**

1.  **Clone o repositório (ou copie os arquivos):**
    ```bash
    git clone <URL_DO_SEU_REPOSITÓRIO>
    cd AppInterno
    ```

2.  **Crie e ative um ambiente virtual:**
    ```bash
    # Windows (PowerShell)
    python -m venv venv
    .\venv\Scripts\Activate.ps1

    # Linux / macOS
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Crie o Banco de Dados:**
    ```bash
    # Windows (PowerShell)
    $env:FLASK_APP = "app.py" 
    flask init-db

    # Linux / macOS
    export FLASK_APP=app.py
    flask init-db
    ```

5.  **Crie a conta de Administrador (Dono):**
    ```bash
    flask create-admin 
    ```
    *(Siga as instruções no terminal para definir usuário, senha, etc.)*

6.  **Execute o aplicativo:**
    ```bash
    # Para rodar apenas no seu PC:
    flask run --debug

    # Para rodar e permitir acesso pela rede local (celulares):
    flask run --debug --host=0.0.0.0 
    ```

7.  **Acesse:**
    * No seu PC: `http://127.0.0.1:5000`
    * Em outros dispositivos na mesma rede: `http://<IP_DO_SEU_PC>:5000` (Encontre o IP com `ipconfig` no Windows ou `ifconfig`/`ip a` no Linux/macOS).

## Estrutura do Projeto