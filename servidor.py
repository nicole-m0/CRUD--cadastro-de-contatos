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

        # INSERE CONTATO
        cursor.execute("""
            INSERT INTO contatos (nome, telefone, email, status_id)
            VALUES (?, ?, ?, ?)
        """, (nome, telefone, email, status_id))
        contato_id = cursor.lastrowid

        # INSERE ENDEREÇO
        cursor.execute("""
            INSERT INTO enderecos (contato_id, rua, cidade, estado)
            VALUES (?, ?, ?, ?)
        """, (contato_id, rua, cidade, estado))

        # LOG DO COMANDO SECO
        sql_seco = "INSERT INTO contatos (nome, telefone, email, status_id) VALUES (?, ?, ?, ?)"
        cursor.execute("""
            INSERT INTO logs (tabela, operacao, descricao, sql_execultado)
            VALUES (?, ?, ?, ?)
        """, ("contatos", "INSERT", f"Contato '{nome}' adicionado", sql_seco))

        conexao.commit()
        conexao.close()
        self.redirect("/listar_cliente")

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

        # Atualiza contato
        conexao_db("""
            UPDATE contatos
            SET nome=?, telefone=?, email=?, status_id=?
            WHERE id=?
        """, (nome, telefone, email, status_id, id_cliente))

        # Atualiza endereço
        conexao_db("""
            UPDATE enderecos
            SET rua=?, cidade=?, estado=?
            WHERE contato_id=?
        """, (rua, cidade, estado, id_cliente))

        # LOG DO COMANDO SECO
        sql_seco = "UPDATE contatos SET nome=?, telefone=?, email=?, status_id=? WHERE id=?"
        conexao_db("""
            INSERT INTO logs (tabela, operacao, descricao, sql_execultado)
            VALUES (?, ?, ?, ?)
        """, ("contatos", "UPDATE", f"Contato '{nome}' editado", sql_seco))

        self.redirect("/listar_cliente")

# ------------------ CLIENTES COMPLETOS ------------------
class ClientesCompletos(tornado.web.RequestHandler):
    def get(self):
        query = "SELECT cliente_id, nome, email, telefone, status, rua, cidade, estado FROM vw_clientes_completos"
        clientes = conexao_db(query)
        self.render("clientes_completos.html", clientes=clientes)

# ------------------ DELETAR CLIENTE ------------------
class DeletarCliente(tornado.web.RequestHandler):
    def post(self):
        id_cliente = self.get_argument("id")

        # LOG DO COMANDO SECO
        sql_seco = "DELETE FROM contatos WHERE id=?"
        conexao_db("""
            INSERT INTO logs (tabela, operacao, descricao, sql_execultado)
            VALUES (?, ?, ?, ?)
        """, ("contatos", "DELETE", f"ID {id_cliente} excluído", sql_seco))

        conexao_db("DELETE FROM contatos WHERE id=?", (id_cliente,))
        self.redirect("/listar_cliente")

# ------------------ HISTÓRICO ------------------
class Historico(tornado.web.RequestHandler):
    def get(self):
        query = "SELECT id, tabela, operacao, data_hora, descricao FROM logs ORDER BY data_hora DESC"
        logs_brutos = conexao_db(query)

        logs = []
        for lid, tabela, operacao, data_hora, descricao in logs_brutos:
            logs.append((lid, tabela, operacao, operacao.lower(), data_hora, descricao))

        self.render("logs.html", logs=logs)

# ------------------ NOVO: VER SQL DA VIEW ------------------
class VerSQLView(tornado.web.RequestHandler):
    def get(self):
        # Código bruto da sua View sem espaços extras no início das linhas
        sql_view = """CREATE VIEW vw_clientes_completos AS
SELECT 
    c.id AS cliente_id,
    c.nome,
    c.email,
    c.telefone,
    s.nome AS status,
    e.rua,
    e.cidade,
    e.estado
FROM contatos c
JOIN status s ON c.status_id = s.id
LEFT JOIN enderecos e ON c.id = e.contato_id;"""

        self.render("ver_sql.html", sql=sql_view)

# ------------------ ATUALIZADO: VER SQL DO HISTÓRICO + TRIGGERS ------------------
class VerSQL(tornado.web.RequestHandler):
    def get(self, log_id):
        resultado = conexao_db("SELECT operacao, sql_execultado FROM logs WHERE id=?", (log_id,))

        if resultado:
            operacao = resultado[0][0].upper()
            sql_salvo = resultado[0][1]

            if not sql_salvo or sql_salvo == "SQL não encontrado no banco de dados.":
                if operacao == "INSERT":
                    crud = """INSERT INTO contatos (nome, telefone, email, status_id)
VALUES (?, ?, ?, ?)"""
                    trigger = """-- TRIGGER RELACIONADA:
CREATE TRIGGER tg_log_insert AFTER INSERT ON contatos
BEGIN
    INSERT INTO logs (tabela, operacao, descricao, data_hora)
    VALUES ('contatos', 'INSERT', 'Contato ' || NEW.nome || ' foi ADICIONADO', DATETIME('now', 'localtime'));
END;"""

                elif operacao == "UPDATE":
                    crud = """UPDATE contatos
SET nome=?, telefone=?, email=?, status_id=?
WHERE id=?"""
                    trigger = """-- TRIGGER RELACIONADA:
CREATE TRIGGER tg_log_update AFTER UPDATE ON contatos
BEGIN
    INSERT INTO logs (tabela, operacao, descricao, data_hora)
    VALUES ('contatos', 'UPDATE', 'Contato ' || NEW.nome || ' foi EDITADO', DATETIME('now', 'localtime'));
END;"""

                elif operacao == "DELETE":
                    crud = """DELETE FROM contatos
WHERE id=?"""
                    trigger = """-- TRIGGER RELACIONADA:
CREATE TRIGGER tg_log_delete AFTER DELETE ON contatos
BEGIN
    INSERT INTO logs (tabela, operacao, descricao, data_hora)
    VALUES ('contatos', 'DELETE', 'Contato ID ' || OLD.id || ' foi EXCLUÍDO', DATETIME('now', 'localtime'));
END;"""
                else:
                    crud = "Operação desconhecida."
                    trigger = ""

                sql = f"{crud}\n\n{trigger}"
            else:
                sql = sql_salvo
        else:
            sql = "Registro não encontrado."

        self.render("ver_sql.html", sql=sql)

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
            (r"/historico/?", Historico),
            (r"/ver_sql/([0-9]+)/?", VerSQL),
            (r"/ver_sql_view/?", VerSQLView),
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