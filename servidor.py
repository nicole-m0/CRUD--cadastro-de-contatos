import os
import sqlite3
import tornado.ioloop
import tornado.web


# ------------------ CONEXÃO COM O BANCO ------------------
def conexao_db(query, valores=None):
    conexao = sqlite3.connect("db/db.sqlite3")
    cursor = conexao.cursor()
    if valores:
        cursor.execute(query, valores)
    else:
        cursor.execute(query)
    resultado = cursor.fetchall()
    conexao.commit()
    conexao.close()
    return resultado


# ------------------ LOGIN ------------------
class Login(tornado.web.RequestHandler):
    def get(self):
        self.render("login.html")

    def post(self):
        usuario = self.get_argument("usuario")
        senha = self.get_argument("senha")
        query = "SELECT * FROM usuarios WHERE usuario=? AND senha=?"
        resultado = conexao_db(query, (usuario, senha))
        if resultado:
            self.redirect("/index")
        else:
            self.write("Usuário ou senha inválidos")


# ------------------ INDEX ------------------
class Index(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")


# ------------------ CLIENTES (LISTAGEM + CADASTRO) ------------------
class Clientes(tornado.web.RequestHandler):
    def get(self):
        busca = self.get_argument("busca", "")
        query = """
            SELECT c.id, c.nome, c.telefone, c.email, c.status_id,
                   e.rua, e.cidade, e.estado
            FROM contatos c
            LEFT JOIN enderecos e ON c.id = e.contato_id
        """
        valores = []
        if busca:
            query += " WHERE c.nome LIKE ?"
            valores.append(f"%{busca}%")
        clientes = conexao_db(query, valores)
        self.render("listar_cliente.html", clientes=clientes, busca=busca)

    def post(self):
        nome = self.get_argument("nome")
        telefone = self.get_argument("telefone")
        email = self.get_argument("email")
        status_id = self.get_argument("status_id")
        rua = self.get_argument("rua")
        cidade = self.get_argument("cidade")
        estado = self.get_argument("estado")

        conexao = sqlite3.connect("db/db.sqlite3")
        cursor = conexao.cursor()
        cursor.execute("""
            INSERT INTO contatos (nome, telefone, email, status_id)
            VALUES (?, ?, ?, ?)
        """, (nome, telefone, email, status_id))
        contato_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO enderecos (contato_id, rua, cidade, estado)
            VALUES (?, ?, ?, ?)
        """, (contato_id, rua, cidade, estado))
        conexao.commit()
        conexao.close()
        self.redirect("/listar_cliente")

# ------------------ VER SQL DA LISTAGEM PRINCIPAL ------------------
class VerSQLListagem(tornado.web.RequestHandler):
    def get(self):
        sql_listagem = """-- SQL QUE GERA A LISTAGEM ABAIXO:
SELECT 
    c.id, 
    c.nome, 
    c.telefone, 
    c.email, 
    c.status_id,
    e.rua, 
    e.cidade, 
    e.estado
FROM contatos c
LEFT JOIN enderecos e ON c.id = e.contato_id;"""
        # Aqui está correto
        self.render("ver_sql.html", sql=sql_listagem, voltar_para="/listar_cliente")

# ------------------ CLIENTES COMPLETOS ------------------
class ClientesCompletos(tornado.web.RequestHandler):
    def get(self):
        clientes = conexao_db("SELECT * FROM vw_clientes_completos")
        self.render("clientes_completos.html", clientes=clientes)

# ------------------ VER SQL DA VIEW ------------------
class VerSQLView(tornado.web.RequestHandler):
    def get(self):
        sql_view = """CREATE VIEW vw_clientes_completos AS
SELECT
    c.id AS cliente_id,
    c.nome,
    c.email,
    c.telefone,
    s.descricao AS status,
    e.rua,
    e.cidade,
    e.estado
FROM contatos c
LEFT JOIN status_cliente s ON c.status_id = s.id
LEFT JOIN enderecos e ON c.id = e.contato_id;"""
        # CORRIGIDO: Agora usamos 'sql_view' que foi definida acima
        self.render("ver_sql.html", sql=sql_view, voltar_para="/listar_cliente")

# ------------------ EDITAR CLIENTE (INLINE) ------------------
class EditarCliente(tornado.web.RequestHandler):
    def post(self):
        id_cliente = self.get_argument("id")
        nome = self.get_argument("nome")
        telefone = self.get_argument("telefone")
        email = self.get_argument("email")
        status_id = self.get_argument("status_id")
        rua = self.get_argument("rua")
        cidade = self.get_argument("cidade")
        estado = self.get_argument("estado")

        conexao_db("""
            UPDATE contatos
            SET nome=?, telefone=?, email=?, status_id=?
            WHERE id=?
        """, (nome, telefone, email, status_id, id_cliente))
        conexao_db("""
            UPDATE enderecos
            SET rua=?, cidade=?, estado=?
            WHERE contato_id=?
        """, (rua, cidade, estado, id_cliente))
        self.redirect("/listar_cliente")


# ------------------ DELETAR CLIENTE ------------------
class DeletarCliente(tornado.web.RequestHandler):
    def post(self):
        id_cliente = self.get_argument("id")
        conexao_db("DELETE FROM contatos WHERE id=?", (id_cliente,))
        self.redirect("/listar_cliente")


# ------------------ HISTÓRICO ------------------
class Historico(tornado.web.RequestHandler):
    def get(self):
        query = "SELECT id, tabela, operacao, data_hora, descricao FROM logs ORDER BY id DESC"
        logs_brutos = conexao_db(query)
        logs = []
        for lid, tabela, operacao, data_hora, descricao in logs_brutos:
            logs.append({
                "id": lid,
                "tabela": tabela,
                "operacao": operacao,
                "data_hora": data_hora,
                "descricao": descricao,
                "classe_css": operacao.lower()
            })
        self.render("logs.html", logs=logs)


# ------------------ VER SQL (COM TRIGGERS) ------------------
class VerSQL(tornado.web.RequestHandler):
    def get(self, log_id):
        resultado = conexao_db("SELECT operacao FROM logs WHERE id=?", (log_id,))

        if resultado:
            operacao = resultado[0][0].upper()

            if operacao == "INSERT":
                crud = "INSERT INTO contatos (nome, telefone, email, status_id) VALUES (?, ?, ?, ?);"
                trigger = """-- TRIGGER EXECUTADA:
CREATE TRIGGER trg_insert_contatos AFTER INSERT ON contatos
BEGIN
    INSERT INTO logs (tabela, operacao, descricao, data_hora)
    VALUES ('contatos', 'INSERT', 'Contato ' || NEW.nome || ' foi ADICIONADO', strftime('%d/%m/%Y', 'now', 'localtime'));
END;"""
            elif operacao == "UPDATE":
                crud = "UPDATE contatos SET nome=?, telefone=?, email=?, status_id=? WHERE id=?;"
                trigger = """-- TRIGGER EXECUTADA:
CREATE TRIGGER trg_update_contatos AFTER UPDATE ON contatos
BEGIN
    INSERT INTO logs (tabela, operacao, descricao, data_hora)
    VALUES ('contatos', 'UPDATE', 'Contato ' || NEW.nome || ' foi EDITADO', strftime('%d/%m/%Y', 'now', 'localtime'));
END;"""
            elif operacao == "DELETE":
                crud = "DELETE FROM contatos WHERE id=?;"
                trigger = """-- TRIGGER EXECUTADA:
CREATE TRIGGER trg_delete_contatos AFTER DELETE ON contatos
BEGIN
    INSERT INTO logs (tabela, operacao, descricao, data_hora)
    VALUES ('contatos', 'DELETE', 'Contato ' || OLD.nome || ' foi EXCLUÍDO', strftime('%d/%m/%Y', 'now', 'localtime'));
END;"""
            else:
                crud = "-- Operação desconhecida."
                trigger = ""

            sql_final = f"{crud}\n\n{trigger}"
        else:
            sql_final = "Registro não encontrado."

        self.render("ver_sql.html", sql=sql_final, voltar_para="/historico")


# ------------------ APLICAÇÃO ------------------
def make_app():
    return tornado.web.Application(
        [
            (r"/", Login),
            (r"/index/?", Index),
            (r"/listar_cliente/?", Clientes),
            (r"/editar_cliente/?", EditarCliente),
            (r"/deletar_cliente/?", DeletarCliente),
            (r"/clientes_completos/?", ClientesCompletos),
            (r"/ver_sql_listagem/?", VerSQLListagem),
            (r"/ver_sql_view/?", VerSQLView),
            (r"/historico/?", Historico),
            (r"/ver_sql/([0-9]+)/?", VerSQL),
        ],
        template_path=os.path.join(os.path.dirname(__file__), "templates"),
        static_path=os.path.join(os.path.dirname(__file__), "static"),
        debug=True
    )


if __name__ == "__main__":
    app = make_app()
    app.listen(8888)
    print("Servidor rodando em http://localhost:8888")
    tornado.ioloop.IOLoop.current().start()