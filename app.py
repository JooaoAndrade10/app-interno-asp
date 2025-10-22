import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory # <-- MUDANÇA AQUI
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import calendar
from sqlalchemy import or_
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# --- 1. Configuração Inicial ---
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'uma-chave-secreta-bem-dificil' 

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Você precisa estar logado para acessar esta página.'
login_manager.login_message_category = 'danger' 

NOMES_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
             "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# --- 2. Modelos do Banco de Dados ---
class Funcionario(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    setor = db.Column(db.String(50), nullable=False) 
    data_nascimento = db.Column(db.Date, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user') 
    escalas_escritorio = db.relationship('EscalaLimpeza', foreign_keys='EscalaLimpeza.funcionario_escritorio_id', backref='func_escritorio', lazy=True)
    escalas_expedicao = db.relationship('EscalaLimpeza', foreign_keys='EscalaLimpeza.funcionario_expedicao_id', backref='func_expedicao', lazy=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    def __repr__(self): return f'<Funcionario {self.nome} ({self.role})>'

@login_manager.user_loader
def load_user(user_id): return Funcionario.query.get(int(user_id))

class Aviso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_postagem = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Feriado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False, unique=True)
    nome = db.Column(db.String(100), nullable=False)

class EscalaLimpeza(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_escala = db.Column(db.Date, nullable=False, unique=True)
    funcionario_escritorio_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False)
    funcionario_expedicao_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False)
    funcionario_escritorio = db.relationship('Funcionario', foreign_keys=[funcionario_escritorio_id])
    funcionario_expedicao = db.relationship('Funcionario', foreign_keys=[funcionario_expedicao_id])

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('index')) 
        return f(*args, **kwargs)
    return decorated_function

# --- 3. Rotas da Aplicação ---

# --- ROTAS DE LOGIN E LOGOUT ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']
        user = Funcionario.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            flash('Usuário ou senha inválidos.', 'danger')
            return redirect(url_for('login'))
        login_user(user, remember=True)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required 
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso.', 'success')
    return redirect(url_for('login'))

# --- ROTA NOVA PARA O SERVICE WORKER ---
@app.route('/sw.js')
def service_worker():
    return send_from_directory('.', 'sw.js', mimetype='application/javascript')
# --- FIM DA ROTA NOVA ---

# --- ROTAS PÚBLICAS (TRANCADAS) ---

@app.route('/')
@login_required 
def index():
    avisos = Aviso.query.order_by(Aviso.data_postagem.desc()).all()
    hoje = date.today()
    aniversariantes_hoje = Funcionario.query.filter(db.extract('month', Funcionario.data_nascimento) == hoje.month, db.extract('day', Funcionario.data_nascimento) == hoje.day).all()
    return render_template('index.html', avisos=avisos, aniversariantes_hoje=aniversariantes_hoje) 

@app.route('/limpeza')
@login_required
def ver_escala():
    escalas = EscalaLimpeza.query.order_by(EscalaLimpeza.data_escala.desc()).all()
    return render_template('ver_escala.html', escalas=escalas)

@app.route('/calendario')
@login_required
def calendario():
    hoje = date.today()
    try: ano = int(request.args.get('ano', hoje.year)); mes = int(request.args.get('mes', hoje.month))
    except ValueError: ano = hoje.year; mes = hoje.month
    mes_anterior, ano_anterior = (mes - 1, ano) if mes > 1 else (12, ano - 1); mes_proximo, ano_proximo = (mes + 1, ano) if mes < 12 else (1, ano + 1)
    links_nav = {'anterior': url_for('calendario', ano=ano_anterior, mes=mes_anterior),'proximo': url_for('calendario', ano=ano_proximo, mes=mes_proximo),'hoje': url_for('calendario')}
    cal = calendar.monthcalendar(ano, mes)
    feriados_bd = Feriado.query.filter(db.extract('year', Feriado.data) == ano, db.extract('month', Feriado.data) == mes).all()
    feriados_mes = {f.data.day: f.nome for f in feriados_bd}
    aniversariantes_bd = Funcionario.query.filter(db.extract('month', Funcionario.data_nascimento) == mes).all()
    aniversarios_mes = {}
    for func in aniversariantes_bd:
        dia = func.data_nascimento.day
        if dia not in aniversarios_mes: aniversarios_mes[dia] = []
        aniversarios_mes[dia].append(func.nome)
    return render_template('calendario.html', calendar_matrix=cal,nome_mes=NOMES_MESES[mes],ano=ano,mes=mes,hoje=hoje,feriados=feriados_mes,aniversarios=aniversarios_mes,nav=links_nav)

# --- ROTAS DO PAINEL ADMIN (TRANCADAS) ---

@app.route('/admin') 
@login_required
@admin_required
def admin_redirect(): return redirect(url_for('admin_panel')) 

@app.route('/admin/funcionarios')
@login_required
@admin_required
def admin_panel():
    funcionarios = Funcionario.query.all()
    return render_template('admin_funcionarios.html', funcionarios=funcionarios)

@app.route('/admin/novo_funcionario', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_funcionario():
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']; role = request.form['role']
        nome = request.form['nome']; setor = request.form['setor']; data_nascimento_str = request.form['data_nascimento']
        user_exists = Funcionario.query.filter_by(username=username).first()
        if user_exists:
            flash(f'O nome de usuário "{username}" já está em uso.', 'danger')
            return redirect(url_for('novo_funcionario'))
        data_nascimento_obj = datetime.strptime(data_nascimento_str, '%Y-%m-%d').date()
        novo_func = Funcionario(username=username, role=role, nome=nome, setor=setor, data_nascimento=data_nascimento_obj)
        novo_func.set_password(password) 
        db.session.add(novo_func); db.session.commit()
        flash(f'Funcionário {nome} ({username}) cadastrado com sucesso!', 'success')
        return redirect(url_for('admin_panel')) 
    return render_template('form_funcionario.html')

@app.route('/admin/funcionario/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_funcionario(id):
    if id == current_user.id:
        flash('Você não pode deletar sua própria conta!', 'danger')
        return redirect(url_for('admin_panel'))
    funcionario_para_deletar = Funcionario.query.get_or_404(id); nome_funcionario = funcionario_para_deletar.nome
    escalas_associadas = EscalaLimpeza.query.filter(or_(EscalaLimpeza.funcionario_escritorio_id == id, EscalaLimpeza.funcionario_expedicao_id == id)).count() 
    if escalas_associadas > 0:
        flash(f'Não é possível excluir {nome_funcionario}, pois ele está associado a {escalas_associadas} escala(s) de limpeza. Remova-o da(s) escala(s) primeiro.', 'danger')
    else:
        try:
            db.session.delete(funcionario_para_deletar); db.session.commit()
            flash(f'Funcionário {nome_funcionario} deletado com sucesso.', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Erro ao deletar funcionário: {e}', 'danger')
    return redirect(url_for('admin_panel'))

@app.route('/admin/novo_aviso', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_aviso():
    if request.method == 'POST':
        titulo = request.form['titulo']; conteudo = request.form['conteudo']
        novo_avs = Aviso(titulo=titulo, conteudo=conteudo); db.session.add(novo_avs); db.session.commit()
        flash('Aviso postado com sucesso!', 'success'); return redirect(url_for('novo_aviso')) 
    avisos = Aviso.query.order_by(Aviso.data_postagem.desc()).all()
    return render_template('form_aviso.html', avisos=avisos)

@app.route('/admin/aviso/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_aviso(id):
    try:
        aviso_para_deletar = Aviso.query.get_or_404(id); titulo_aviso = aviso_para_deletar.titulo
        db.session.delete(aviso_para_deletar); db.session.commit()
        flash(f'Aviso "{titulo_aviso}" deletado com sucesso.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Erro ao deletar aviso: {e}', 'danger')
    return redirect(url_for('novo_aviso'))

@app.route('/admin/escala', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_escala():
    if request.method == 'POST':
        try:
            data_escala_str = request.form['data_escala']; id_escritorio = request.form['funcionario_escritorio']; id_expedicao = request.form['funcionario_expedicao']
            data_escala_obj = datetime.strptime(data_escala_str, '%Y-%m-%d').date()
            nova_escala = EscalaLimpeza(data_escala=data_escala_obj, funcionario_escritorio_id=id_escritorio, funcionario_expedicao_id=id_expedicao)
            db.session.add(nova_escala); db.session.commit()
            flash('Escala de limpeza salva com sucesso!', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Erro ao salvar escala: A data {data_escala_str} já está cadastrada.', 'danger')
        return redirect(url_for('admin_escala')) 
    funcs_escritorio = Funcionario.query.filter_by(setor='Escritorio').all()
    funcs_expedicao = Funcionario.query.filter_by(setor='Expedicao').all()
    escalas_cadastradas = EscalaLimpeza.query.order_by(EscalaLimpeza.data_escala.desc()).all()
    return render_template('admin_escala.html', funcs_escritorio=funcs_escritorio, funcs_expedicao=funcs_expedicao, escalas=escalas_cadastradas)

@app.route('/admin/escala/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_escala(id):
    try:
        escala_para_deletar = EscalaLimpeza.query.get_or_404(id); data_escala = escala_para_deletar.data_escala.strftime('%d/%m/%Y')
        db.session.delete(escala_para_deletar); db.session.commit()
        flash(f'Escala do dia {data_escala} deletada com sucesso.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Erro ao deletar escala: {e}', 'danger')
    return redirect(url_for('admin_escala'))

@app.route('/admin/calendario', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_calendario():
    if request.method == 'POST':
        try:
            data_feriado_str = request.form['data_feriado']; nome_feriado = request.form['nome_feriado']
            data_feriado_obj = datetime.strptime(data_feriado_str, '%Y-%m-%d').date()
            novo_feriado = Feriado(data=data_feriado_obj, nome=nome_feriado)
            db.session.add(novo_feriado); db.session.commit()
            flash(f'Feriado "{nome_feriado}" salvo com sucesso!', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Erro ao salvar feriado: A data {data_feriado_str} já está cadastrada.', 'danger')
        return redirect(url_for('admin_calendario'))
    feriados = Feriado.query.order_by(Feriado.data.asc()).all()
    return render_template('admin_calendario.html', feriados=feriados)

@app.route('/admin/feriado/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_feriado(id):
    try:
        feriado_para_deletar = Feriado.query.get_or_404(id); nome_feriado = feriado_para_deletar.nome
        db.session.delete(feriado_para_deletar); db.session.commit()
        flash(f'Feriado "{nome_feriado}" deletado com sucesso.', 'success')
    except Exception as e:
        db.session.rollback(); flash(f'Erro ao deletar feriado: {e}', 'danger')
    return redirect(url_for('admin_calendario'))


# --- 4. Comandos de CLI ---
@app.cli.command('init-db')
def init_db_command():
    db.create_all()
    print('Banco de dados inicializado!')

@app.cli.command('create-admin')
def create_admin_command():
    print("--- Criando Conta de Administrador (Dono) ---")
    username = input("Digite o nome de usuário para o Dono: "); password = input("Digite a senha: ")
    nome = input("Digite o nome completo do Dono: "); setor = input("Setor (Ex: Escritorio): ")
    nascimento_str = input("Data de Nascimento (AAAA-MM-DD): ")
    if not username or not password or not nome: print("Usuário, senha e nome são obrigatórios."); return
    user_exists = Funcionario.query.filter_by(username=username).first()
    if user_exists: print(f'Erro: Usuário "{username}" já existe.'); return
    try:
        nascimento_obj = datetime.strptime(nascimento_str, '%Y-%m-%d').date()
        admin_user = Funcionario(username=username,nome=nome,setor=setor,data_nascimento=nascimento_obj,role='admin')
        admin_user.set_password(password) 
        db.session.add(admin_user); db.session.commit()
        print(f'Usuário Administrador "{username}" criado com sucesso!')
    except Exception as e:
        db.session.rollback(); print(f"Erro ao criar admin: {e}")