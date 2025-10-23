import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timedelta
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

# --- Filtro Jinja2 Customizado ---
def format_timedelta(value):
    if not isinstance(value, timedelta): return value
    total_seconds = int(value.total_seconds()); sign = '-' if total_seconds < 0 else ''; total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600); minutes, seconds = divmod(remainder, 60)
    return f'{sign}{hours:02}:{minutes:02}:{seconds:02}'
app.jinja_env.filters['format_timedelta'] = format_timedelta

# --- Configuração Flask-Login ---
login_manager = LoginManager(); login_manager.init_app(app); login_manager.login_view = 'login'
login_manager.login_message = 'Você precisa estar logado para acessar esta página.'; login_manager.login_message_category = 'danger'

NOMES_MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]

# --- 2. Modelos DB ---
class Funcionario(db.Model, UserMixin):
    id=db.Column(db.Integer, primary_key=True); nome=db.Column(db.String(100), nullable=False); setor=db.Column(db.String(50), nullable=False); data_nascimento=db.Column(db.Date, nullable=False); username=db.Column(db.String(80), unique=True, nullable=False); password_hash=db.Column(db.String(256), nullable=False); role=db.Column(db.String(20), nullable=False, default='user'); grupo_sabado=db.Column(db.String(1), nullable=True); horario_especial_09=db.Column(db.Boolean, nullable=False, default=False); registros_ponto=db.relationship('RegistroPonto', backref='funcionario', lazy='dynamic'); escalas_escritorio=db.relationship('EscalaLimpeza', foreign_keys='EscalaLimpeza.funcionario_escritorio_id', backref='func_escritorio', lazy=True); escalas_expedicao=db.relationship('EscalaLimpeza', foreign_keys='EscalaLimpeza.funcionario_expedicao_id', backref='func_expedicao', lazy=True)
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)
    # --- __repr__ CORRIGIDO ---
    def __repr__(self):
        return f'<Funcionario {self.nome} ({self.role})>'

@login_manager.user_loader
def load_user(user_id):
    return Funcionario.query.get(int(user_id))

class Aviso(db.Model):
    id=db.Column(db.Integer, primary_key=True); titulo=db.Column(db.String(200), nullable=False); conteudo=db.Column(db.Text, nullable=False); data_postagem=db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    # --- __repr__ CORRIGIDO ---
    def __repr__(self):
        return f'<Aviso {self.titulo}>'

class Feriado(db.Model):
    id=db.Column(db.Integer, primary_key=True); data=db.Column(db.Date, nullable=False, unique=True); nome=db.Column(db.String(100), nullable=False)
    # --- __repr__ CORRIGIDO ---
    def __repr__(self):
        return f'<Feriado {self.nome} em {self.data}>'

class EscalaLimpeza(db.Model):
    id=db.Column(db.Integer, primary_key=True); data_escala=db.Column(db.Date, nullable=False, unique=True); funcionario_escritorio_id=db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False); funcionario_expedicao_id=db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False); funcionario_escritorio=db.relationship('Funcionario', foreign_keys=[funcionario_escritorio_id]); funcionario_expedicao=db.relationship('Funcionario', foreign_keys=[funcionario_expedicao_id])
    # --- __repr__ CORRIGIDO ---
    def __repr__(self):
        return f'<Escala {self.data_escala}>'

class RegistroPonto(db.Model):
    id=db.Column(db.Integer, primary_key=True); funcionario_id=db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False); timestamp_entrada=db.Column(db.DateTime, nullable=False, default=datetime.utcnow); timestamp_saida=db.Column(db.DateTime, nullable=True); observacao=db.Column(db.String(200), nullable=True)
    # --- __repr__ CORRIGIDO (Onde estava o erro!) ---
    def __repr__(self):
        saida_str = self.timestamp_saida.strftime('%H:%M') if self.timestamp_saida else 'Aberto'
        entrada_local = self.timestamp_entrada # Idealmente converter fuso
        return f'<Ponto {self.funcionario.nome} {entrada_local.strftime("%d/%m %H:%M")} - {saida_str}>'

# --- Lógica Banco de Horas ---
DATA_REFERENCIA_GRUPO_A = date(2025, 1, 1); SEMANA_REFERENCIA = DATA_REFERENCIA_GRUPO_A.isocalendar()[1]
# --- get_expected_work_duration CORRIGIDO ---
def get_expected_work_duration(funcionario, target_date):
    if target_date.weekday() == 6: return timedelta(0)
    if Feriado.query.filter_by(data=target_date).first(): return timedelta(0)
    target_week = target_date.isocalendar()[1]; semana_grupo = 'A' if (target_week - SEMANA_REFERENCIA) % 2 == 0 else 'B'; day_of_week = target_date.weekday(); horario_inicio = 9 if funcionario.horario_especial_09 else 8
    if day_of_week == 5:
        if funcionario.grupo_sabado and funcionario.grupo_sabado == semana_grupo: return timedelta(hours=4)
        else: return timedelta(0)
    else:
        trabalha_sabado_na_semana = (funcionario.grupo_sabado and funcionario.grupo_sabado == semana_grupo)
        if trabalha_sabado_na_semana: return timedelta(hours=7) if horario_inicio == 9 else timedelta(hours=8)
        else:
            if day_of_week <= 3: return timedelta(hours=8) if horario_inicio == 9 else timedelta(hours=9)
            elif day_of_week == 4: return timedelta(hours=7) if horario_inicio == 9 else timedelta(hours=8)
            else: return timedelta(0)

# --- Decorator @admin_required CORRIGIDO ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Você não tem permissão para acessar esta página.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Function para parse de datetime CORRIGIDO ---
def parse_datetime_local(date_str, time_str):
    if not date_str or not time_str: return None
    try: return datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
    except ValueError: return None

# --- 3. Rotas ---
# (Todas as rotas com indentação revisada e decorators em linhas separadas)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username']; password = request.form['password']; user = Funcionario.query.filter_by(username=username).first()
        if not user or not user.check_password(password): flash('Usuário ou senha inválidos.', 'danger'); return redirect(url_for('login'))
        login_user(user, remember=True); return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user(); flash('Você foi desconectado com sucesso.', 'success'); return redirect(url_for('login'))

@app.route('/sw.js')
def service_worker():
    return send_from_directory('.', 'sw.js', mimetype='application/javascript')

@app.route('/')
@login_required
def index():
    avisos = Aviso.query.order_by(Aviso.data_postagem.desc()).all(); hoje = date.today(); aniversariantes_hoje = Funcionario.query.filter(db.extract('month', Funcionario.data_nascimento) == hoje.month, db.extract('day', Funcionario.data_nascimento) == hoje.day).all()
    return render_template('index.html', avisos=avisos, aniversariantes_hoje=aniversariantes_hoje)

@app.route('/limpeza')
@login_required
def ver_escala():
    escalas = EscalaLimpeza.query.order_by(EscalaLimpeza.data_escala.desc()).all()
    return render_template('ver_escala.html', escalas=escalas)

@app.route('/calendario')
@login_required
def calendario():
    hoje = date.today(); ano = int(request.args.get('ano', hoje.year)); mes = int(request.args.get('mes', hoje.month))
    mes_anterior, ano_anterior = (mes - 1, ano) if mes > 1 else (12, ano - 1); mes_proximo, ano_proximo = (mes + 1, ano) if mes < 12 else (1, ano + 1)
    links_nav = {'anterior': url_for('calendario', ano=ano_anterior, mes=mes_anterior),'proximo': url_for('calendario', ano=ano_proximo, mes=mes_proximo),'hoje': url_for('calendario')}
    cal = calendar.monthcalendar(ano, mes); feriados_bd = Feriado.query.filter(db.extract('year', Feriado.data) == ano, db.extract('month', Feriado.data) == mes).all(); feriados_mes = {f.data.day: f.nome for f in feriados_bd}; aniversariantes_bd = Funcionario.query.filter(db.extract('month', Funcionario.data_nascimento) == mes).all(); aniversarios_mes = {}; [aniversarios_mes.setdefault(f.data_nascimento.day, []).append(f.nome) for f in aniversariantes_bd]
    return render_template('calendario.html', calendar_matrix=cal,nome_mes=NOMES_MESES[mes],ano=ano,mes=mes,hoje=hoje,feriados=feriados_mes,aniversarios=aniversarios_mes,nav=links_nav)

@app.route('/ponto')
@login_required
def ponto_usuario():
    ultimo_registro = current_user.registros_ponto.order_by(RegistroPonto.timestamp_entrada.desc()).first(); status_atual = "Fora do expediente"; botao_texto = "Registrar Entrada"; botao_classe = "entrada"
    if ultimo_registro and not ultimo_registro.timestamp_saida: entrada_local_str = ultimo_registro.timestamp_entrada.strftime('%H:%M'); status_atual = f"Trabalhando desde {entrada_local_str}"; botao_texto = "Registrar Saída"; botao_classe = "saida"
    data_limite = datetime.utcnow() - timedelta(days=30); registros_bd = current_user.registros_ponto.filter(RegistroPonto.timestamp_entrada >= data_limite).order_by(RegistroPonto.timestamp_entrada.desc()).all()
    historico_calculado = []; saldo_total = timedelta(0); registros_por_dia = {}
    for r in registros_bd: data_registro = r.timestamp_entrada.date(); registros_por_dia.setdefault(data_registro, []).append(r)
    datas_ordenadas = sorted(registros_por_dia.keys(), reverse=True)
    for dia in datas_ordenadas:
        registros_do_dia = registros_por_dia[dia]; tempo_trabalhado_dia = timedelta(0); entradas_saidas_formatadas = []
        for r in sorted(registros_do_dia, key=lambda x: x.timestamp_entrada): entrada_str = r.timestamp_entrada.strftime('%H:%M:%S'); saida_str = r.timestamp_saida.strftime('%H:%M:%S') if r.timestamp_saida else "(Aberto)"; entradas_saidas_formatadas.append(f"{entrada_str} - {saida_str}");
        if r.timestamp_saida: tempo_trabalhado_dia += (r.timestamp_saida - r.timestamp_entrada)
        horas_esperadas_dia = get_expected_work_duration(current_user, dia); saldo_dia = tempo_trabalhado_dia - horas_esperadas_dia; saldo_total += saldo_dia; historico_calculado.append({'data': dia.strftime('%d/%m/%Y'),'registros': "<br>".join(entradas_saidas_formatadas),'trabalhado': tempo_trabalhado_dia,'esperado': horas_esperadas_dia,'saldo_dia': saldo_dia})
    return render_template('ponto_usuario.html', status_atual=status_atual, botao_texto=botao_texto, botao_classe=botao_classe, historico=historico_calculado, saldo_total=saldo_total)

@app.route('/registrar_ponto', methods=['POST'])
@login_required
def registrar_ponto():
    agora = datetime.utcnow(); registro_aberto = current_user.registros_ponto.filter(RegistroPonto.timestamp_saida == None).order_by(RegistroPonto.timestamp_entrada.desc()).first()
    if registro_aberto: registro_aberto.timestamp_saida = agora; agora_local_str = agora.strftime("%H:%M:%S"); flash(f'Saída registrada às {agora_local_str}.', 'success')
    else: novo_registro = RegistroPonto(funcionario_id=current_user.id, timestamp_entrada=agora); db.session.add(novo_registro); agora_local_str = agora.strftime("%H:%M:%S"); flash(f'Entrada registrada às {agora_local_str}.', 'success')
    db.session.commit(); return redirect(url_for('ponto_usuario'))

@app.route('/admin')
@login_required
@admin_required
def admin_redirect():
    return redirect(url_for('admin_panel'))

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
        # --- Campos de Login ---
        username = request.form['username']; password = request.form['password']; role = request.form['role']
        # --- Campos Pessoais ---
        nome = request.form['nome']; setor = request.form['setor']; data_nascimento_str = request.form['data_nascimento']
        # --- Campos Horário ---
        grupo_sabado = request.form.get('grupo_sabado'); horario_especial_str = request.form['horario_especial_09']
        horario_especial_09 = horario_especial_str == 'True'
        if not grupo_sabado: grupo_sabado = None

        # --- Validação de Username (ANTES DO TRY) ---
        user_exists = Funcionario.query.filter_by(username=username).first()
        if user_exists:
            flash(f'O nome de usuário "{username}" já está em uso.', 'danger')
            # Retorna para o formulário mantendo os dados digitados
            return render_template('form_funcionario.html', form_data=request.form)

        # --- Criação do Funcionário (DENTRO DO TRY) ---
        try:
            data_nascimento_obj = datetime.strptime(data_nascimento_str, '%Y-%m-%d').date()
            novo_func = Funcionario(
                username=username, role=role, nome=nome, setor=setor, data_nascimento=data_nascimento_obj,
                grupo_sabado=grupo_sabado, horario_especial_09=horario_especial_09)
            novo_func.set_password(password)
            db.session.add(novo_func); db.session.commit()
            flash(f'Funcionário {nome} ({username}) cadastrado com sucesso!', 'success')
            return redirect(url_for('admin_panel')) # Redireciona para a lista após sucesso
        except ValueError:
             flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
             # Retorna para o formulário mantendo os dados
             return render_template('form_funcionario.html', form_data=request.form)
        except Exception as e:
             db.session.rollback()
             flash(f'Erro inesperado ao salvar funcionário: {e}', 'danger')
             # Retorna para o formulário mantendo os dados
             return render_template('form_funcionario.html', form_data=request.form)

    # Se for GET, apenas mostra o formulário
    return render_template('form_funcionario.html', form_data={})

@app.route('/admin/funcionario/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_funcionario(id):
    if id == current_user.id: flash('Você não pode deletar sua própria conta!', 'danger'); return redirect(url_for('admin_panel'))
    f = Funcionario.query.get_or_404(id); nome_f = f.nome; e = EscalaLimpeza.query.filter(or_(EscalaLimpeza.funcionario_escritorio_id == id, EscalaLimpeza.funcionario_expedicao_id == id)).count()
    if e > 0: flash(f'Não é possível excluir {nome_f}, pois ele está associado a {e} escala(s) de limpeza.', 'danger')
    else:
        try: db.session.delete(f); db.session.commit(); flash(f'Funcionário {nome_f} deletado com sucesso.', 'success')
        except Exception as ex: db.session.rollback(); flash(f'Erro ao deletar funcionário: {ex}', 'danger')
    return redirect(url_for('admin_panel'))

@app.route('/admin/novo_aviso', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_aviso():
    if request.method == 'POST': titulo = request.form['titulo']; conteudo = request.form['conteudo']; novo_avs = Aviso(titulo=titulo, conteudo=conteudo); db.session.add(novo_avs); db.session.commit(); flash('Aviso postado com sucesso!', 'success'); return redirect(url_for('novo_aviso'))
    avisos = Aviso.query.order_by(Aviso.data_postagem.desc()).all(); return render_template('form_aviso.html', avisos=avisos)

@app.route('/admin/aviso/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_aviso(id):
    try: aviso = Aviso.query.get_or_404(id); titulo = aviso.titulo; db.session.delete(aviso); db.session.commit(); flash(f'Aviso "{titulo}" deletado com sucesso.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Erro ao deletar aviso: {e}', 'danger')
    return redirect(url_for('novo_aviso'))

@app.route('/admin/escala', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_escala():
    if request.method == 'POST':
        d_str = request.form['data_escala']; id_esc = request.form['funcionario_escritorio']; id_exp = request.form['funcionario_expedicao']
        try: d_obj = datetime.strptime(d_str, '%Y-%m-%d').date(); n_esc = EscalaLimpeza(data_escala=d_obj, funcionario_escritorio_id=id_esc, funcionario_expedicao_id=id_exp); db.session.add(n_esc); db.session.commit(); flash('Escala de limpeza salva com sucesso!', 'success')
        except ValueError: flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
        except Exception as e: db.session.rollback(); flash(f'Erro ao salvar escala: A data {d_str} já está cadastrada.', 'danger')
        return redirect(url_for('admin_escala'))
    f_esc = Funcionario.query.filter_by(setor='Escritorio').all(); f_exp = Funcionario.query.filter_by(setor='Expedicao').all(); e_cad = EscalaLimpeza.query.order_by(EscalaLimpeza.data_escala.desc()).all()
    return render_template('admin_escala.html', funcs_escritorio=f_esc, funcs_expedicao=f_exp, escalas=e_cad)

@app.route('/admin/escala/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_escala(id):
    try: esc = EscalaLimpeza.query.get_or_404(id); data_esc = esc.data_escala.strftime('%d/%m/%Y'); db.session.delete(esc); db.session.commit(); flash(f'Escala do dia {data_esc} deletada com sucesso.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Erro ao deletar escala: {e}', 'danger')
    return redirect(url_for('admin_escala'))

# --- ROTAS ADMIN PONTO (COM CRUD e CÁLCULO DE SALDO) ---
@app.route('/admin/ponto')
@login_required
@admin_required
def admin_ponto():
    # Busca funcionários para filtro (sem mudanças)
    funcionarios = Funcionario.query.order_by(Funcionario.nome).all()
    selected_funcionario_id = request.args.get('funcionario_id', type=int)
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Query base (sem mudanças)
    query = RegistroPonto.query.options(db.joinedload(RegistroPonto.funcionario))

    # Filtros (sem mudanças)
    if selected_funcionario_id:
        query = query.filter(RegistroPonto.funcionario_id == selected_funcionario_id)
    start_date = None
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(RegistroPonto.timestamp_entrada >= start_date)
        except ValueError:
            flash('Formato inválido para data inicial.', 'danger')
    end_date = None
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date_exclusive = end_date + timedelta(days=1)
            query = query.filter(RegistroPonto.timestamp_entrada < end_date_exclusive)
        except ValueError:
            flash('Formato inválido para data final.', 'danger')

    # Ordena para agrupar (sem mudanças)
    registros_filtrados = query.order_by(RegistroPonto.funcionario_id, RegistroPonto.timestamp_entrada).all()

    # Processamento e Agrupamento (REVISADO COM ATENÇÃO ÀS F-STRINGS)
    dados_por_funcionario_dia = {}
    for registro in registros_filtrados:
        func_id = registro.funcionario_id
        func_nome = registro.funcionario.nome
        dia_registro = registro.timestamp_entrada.date() # Idealmente converter fuso

        if func_id not in dados_por_funcionario_dia:
            dados_por_funcionario_dia[func_id] = {'nome': func_nome, 'dias': {}}
        if dia_registro not in dados_por_funcionario_dia[func_id]['dias']:
            dados_por_funcionario_dia[func_id]['dias'][dia_registro] = {
                'data_str': dia_registro.strftime('%d/%m/%Y'),
                'registros_detalhados': [],
                'trabalhado': timedelta(0),
                'esperado': get_expected_work_duration(registro.funcionario, dia_registro),
                'saldo_dia': timedelta(0)
            }

        entrada_str = registro.timestamp_entrada.strftime('%H:%M:%S')
        saida_str = registro.timestamp_saida.strftime('%H:%M:%S') if registro.timestamp_saida else "(Aberto)"
        
        # Guarda ID e strings separadamente
        dados_por_funcionario_dia[func_id]['dias'][dia_registro]['registros_detalhados'].append({
            'id': registro.id,
            'entrada': entrada_str,
            'saida': saida_str
        })

        if registro.timestamp_saida:
            duracao = registro.timestamp_saida - registro.timestamp_entrada
            dados_por_funcionario_dia[func_id]['dias'][dia_registro]['trabalhado'] += duracao

    # Calcula saldo e prepara string HTML final (F-STRINGS REVISADAS)
    for func_id in dados_por_funcionario_dia:
        for dia in dados_por_funcionario_dia[func_id]['dias']:
            dados_dia = dados_por_funcionario_dia[func_id]['dias'][dia]
            dados_dia['saldo_dia'] = dados_dia['trabalhado'] - dados_dia['esperado']
            
            html_registros = []
            for reg_detalhe in dados_dia['registros_detalhados']:
                # Garante que as URLs estão corretas
                edit_link = url_for('edit_ponto_manual', id=reg_detalhe['id'])
                delete_url = url_for('delete_ponto_manual', id=reg_detalhe['id'])
                # Revisa as aspas na confirmação JS
                confirm_msg = f"Deletar este registro? Entrada: {reg_detalhe['entrada']}"
                # Usa aspas simples externamente na f-string, duplas internamente no HTML/JS
                registro_html = f''' 
                <div class="registro-item">
                    <span>{reg_detalhe['entrada']} - {reg_detalhe['saida']}</span>
                    <div class="registro-actions">
                        <a href="{edit_link}" class="edit-button-small">E</a>
                        <form action="{delete_url}" method="POST" class="delete-form-small" 
                              onsubmit="return confirm('{confirm_msg}');">
                            <button type="submit" class="delete-button-small">X</button>
                        </form>
                    </div>
                </div>
                '''
                html_registros.append(registro_html.strip())
            dados_dia['registros_str_html'] = "".join(html_registros)

    lista_final_admin = []
    for func_id in sorted(dados_por_funcionario_dia, key=lambda fid: dados_por_funcionario_dia[fid]['nome']):
        info_func = dados_por_funcionario_dia[func_id]
        dias_ordenados = sorted(info_func['dias'].items(), key=lambda item: item[0], reverse=True)
        lista_final_admin.append({'nome_funcionario': info_func['nome'], 'resumo_dias': [d[1] for d in dias_ordenados]})

    return render_template('admin_ponto.html',
                           resumo_admin=lista_final_admin,
                           funcionarios=funcionarios,
                           selected_funcionario_id=selected_funcionario_id,
                           start_date=start_date_str,
                           end_date=end_date_str)

@app.route('/admin/ponto/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_ponto_manual():
    if request.method == 'POST':
        f_id = request.form.get('funcionario_id', type=int); d_str = request.form.get('data'); e_str = request.form.get('entrada'); s_str = request.form.get('saida'); obs = request.form.get('observacao')
        if not f_id or not d_str or not e_str: flash('Funcionário, Data e Hora Entrada obrigatórios.', 'danger'); funcs = Funcionario.query.order_by(Funcionario.nome).all(); return render_template('form_ponto.html', funcionarios=funcs, registro=None, form_data=request.form)
        e_dt = parse_datetime_local(d_str, e_str); s_dt = parse_datetime_local(d_str, s_str)
        if e_dt is None: flash('Formato inválido Entrada.', 'danger'); funcs = Funcionario.query.order_by(Funcionario.nome).all(); return render_template('form_ponto.html', funcionarios=funcs, registro=None, form_data=request.form)
        if s_str and s_dt is None: flash('Formato inválido Saída.', 'danger'); funcs = Funcionario.query.order_by(Funcionario.nome).all(); return render_template('form_ponto.html', funcionarios=funcs, registro=None, form_data=request.form)
        if s_dt and e_dt >= s_dt: flash('Saída deve ser posterior à Entrada.', 'danger'); funcs = Funcionario.query.order_by(Funcionario.nome).all(); return render_template('form_ponto.html', funcionarios=funcs, registro=None, form_data=request.form)
        try: n_reg = RegistroPonto(funcionario_id=f_id, timestamp_entrada=e_dt, timestamp_saida=s_dt, observacao=obs); db.session.add(n_reg); db.session.commit(); flash('Registro adicionado com sucesso.', 'success'); return redirect(url_for('admin_ponto'))
        except Exception as e: db.session.rollback(); flash(f'Erro ao adicionar: {e}', 'danger')
    funcs = Funcionario.query.order_by(Funcionario.nome).all(); return render_template('form_ponto.html', funcionarios=funcs, registro=None, form_data={})

@app.route('/admin/ponto/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_ponto_manual(id):
    reg = RegistroPonto.query.get_or_404(id); funcs = Funcionario.query.order_by(Funcionario.nome).all()
    if request.method == 'POST':
        f_id = request.form.get('funcionario_id', type=int); d_str = request.form.get('data'); e_str = request.form.get('entrada'); s_str = request.form.get('saida'); obs = request.form.get('observacao')
        if not f_id or not d_str or not e_str: flash('Funcionário, Data e Hora Entrada obrigatórios.', 'danger'); return render_template('form_ponto.html', funcionarios=funcs, registro=reg, form_data=request.form)
        e_dt = parse_datetime_local(d_str, e_str); s_dt = parse_datetime_local(d_str, s_str)
        if e_dt is None: flash('Formato inválido Entrada.', 'danger'); return render_template('form_ponto.html', funcionarios=funcs, registro=reg, form_data=request.form)
        if s_str and s_dt is None: flash('Formato inválido Saída.', 'danger'); return render_template('form_ponto.html', funcionarios=funcs, registro=reg, form_data=request.form)
        if s_dt and e_dt >= s_dt: flash('Saída deve ser posterior à Entrada.', 'danger'); return render_template('form_ponto.html', funcionarios=funcs, registro=reg, form_data=request.form)
        try: reg.funcionario_id = f_id; reg.timestamp_entrada = e_dt; reg.timestamp_saida = s_dt; reg.observacao = obs; db.session.commit(); flash('Registro atualizado.', 'success'); return redirect(url_for('admin_ponto'))
        except Exception as e: db.session.rollback(); flash(f'Erro ao atualizar: {e}', 'danger')
    form_data = {'funcionario_id': reg.funcionario_id, 'data': reg.timestamp_entrada.strftime('%Y-%m-%d'), 'entrada': reg.timestamp_entrada.strftime('%H:%M'), 'saida': reg.timestamp_saida.strftime('%H:%M') if reg.timestamp_saida else '', 'observacao': reg.observacao or ''}
    return render_template('form_ponto.html', funcionarios=funcs, registro=reg, form_data=form_data)

@app.route('/admin/ponto/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_ponto_manual(id):
    try: reg = RegistroPonto.query.get_or_404(id); db.session.delete(reg); db.session.commit(); flash('Registro deletado.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Erro ao deletar: {e}', 'danger')
    return redirect(url_for('admin_ponto'))

@app.route('/admin/calendario', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_calendario():
    if request.method == 'POST':
        d_str = request.form['data_feriado']; nome_f = request.form['nome_feriado']
        try: d_obj = datetime.strptime(d_str, '%Y-%m-%d').date(); n_fer = Feriado(data=d_obj, nome=nome_f); db.session.add(n_fer); db.session.commit(); flash(f'Feriado "{nome_f}" salvo com sucesso!', 'success')
        except ValueError: flash('Formato de data inválido. Use AAAA-MM-DD.', 'danger')
        except Exception as e: db.session.rollback(); flash(f'Erro ao salvar feriado: A data {d_str} já está cadastrada.', 'danger')
        return redirect(url_for('admin_calendario'))
    feriados = Feriado.query.order_by(Feriado.data.asc()).all(); return render_template('admin_calendario.html', feriados=feriados)

@app.route('/admin/feriado/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_feriado(id):
    try: fer = Feriado.query.get_or_404(id); nome_f = fer.nome; db.session.delete(fer); db.session.commit(); flash(f'Feriado "{nome_f}" deletado com sucesso.', 'success')
    except Exception as e: db.session.rollback(); flash(f'Erro ao deletar feriado: {e}', 'danger')
    return redirect(url_for('admin_calendario'))


# --- 4. Comandos de CLI ---
@app.cli.command('init-db')
def init_db_command():
    db.create_all(); print('Banco de dados inicializado!')

@app.cli.command('create-admin')
def create_admin_command():
    print("--- Criando Conta de Administrador (Dono) ---"); u = input("Usuário: "); p = input("Senha: "); n = input("Nome Completo: "); s = input("Setor: "); nasc_str = input("Nascimento (AAAA-MM-DD): ")
    g_sab = input("Grupo Sábado (A/B ou deixe em branco): "); h_esp_str = input("Entra às 09:00? (S/N): ").upper()
    if not u or not p or not n: print("Usuário, senha e nome obrigatórios."); return
    if Funcionario.query.filter_by(username=u).first(): print(f'Erro: Usuário "{u}" já existe.'); return
    g_sab = g_sab.upper() if g_sab else None;
    if g_sab and g_sab not in ['A', 'B']: print("Erro: Grupo Sábado deve ser 'A' ou 'B'."); return
    if h_esp_str not in ['S', 'N']: print("Erro: Horário especial deve ser 'S' ou 'N'."); return
    horario_especial_09 = h_esp_str == 'S'
    try:
        nasc_obj = datetime.strptime(nasc_str, '%Y-%m-%d').date(); admin = Funcionario(username=u,nome=n,setor=s,data_nascimento=nasc_obj,role='admin', grupo_sabado=g_sab, horario_especial_09=horario_especial_09)
        admin.set_password(p); db.session.add(admin); db.session.commit(); print(f'Usuário Administrador "{u}" criado com sucesso!')
    except ValueError: print("Erro: Formato de data inválido. Use AAAA-MM-DD.")
    except Exception as e: db.session.rollback(); print(f"Erro ao criar admin: {e}")

# --- Execução direta (para testes, se necessário) ---
# if __name__ == '__main__':
#     # Lembre-se de remover host='0.0.0.0' se não precisar acessar pela rede
#     app.run(debug=True, host='0.0.0.0', port=5000)