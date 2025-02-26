"""
autor: Samuel Auces
Descripcion:
estte codigo pertenece a una azure function, crea un bot de telegram para enviar y escuchar mensajes de un grupo de vecinos en un edificio de departamentos.
en el edificio constantemente se presnetan fugas de agua debido a descuidos de vecinos.
en el tinaco del edifioc se coloca un sensor de flujo de agua y cada que este detecta una fuga (cuando se presenta un flujo durante mas de cierto tiempo)
el sensor de agua esta conectado a un ESP32 (microcontrolador) y este envia una HTTP request que actua como mensaje al grupo de telegram, en el cual esta el bot escuchando.
una vez que el bot recibe el comando "/fuga" (solo puede ser enviado por determinado usuario aka microcontrolador) el bot de telegram (azure function),
ejecuta una serie de funciones para cerrar la llave de paso y evitar mas fugas, notificar a los vecinos, ofreciendo una serie de opciones, como :
en base 
-Confirmo: el usuaario ha verificado que no hay fugas, una vez que todos confirmen la llave de paso se abrira y todos tendran servicio de agua de nuevo
-Comodin: en caso necesario los usuarios/vecinos podran usar el servicio de agua por 15 mins a pesar de haber fuga (solo se puede usar 1 vez por vecino)
-Estado: sirve para ver cuantos vecinos faltan por confirmar y si hay o no fuga
-Help: presenta las opciones ya mencionadas
"""



from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext,ContextTypes,ApplicationBuilder
import logging
import azure.functions as func
import json
import aiohttp
import os,requests
from azure.data.tables import TableServiceClient

vecinos=os.environ["VECINOS"].split(",")
# Activa el logging para depuración
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
TOKEN=os.environ["TOKEN"]



async def echo(update: Update, context: CallbackContext) -> None:
    #Responde repitiendo el mensaje del usuario.
    try:
        await update.message.reply_text(update.message.text)
    except Exception as e:
        logging.info(f"ocurrio algo insesperado: {e}")
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Lo siento, no entiendo ese comando. Usa /ayuda para ver las opciones disponibles, recuerda usar '/' antes de la palabra")

# Función de manejo de solicitudes HTTP para Azure Functions
async def telegram_webhook(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data=req.get_json()
        if not telegram_app.bot:  # Verificar si el bot no está inicializado
            logging.info("no inicio")
            await telegram_app.initialize()  # Inicializar el bot antes de procesar la actualización
        logging.info("se va a ejecutar la funcion update")
        update = Update.de_json(data, telegram_app.bot)
        logging.info("debug")
        await telegram_app.initialize()
        await telegram_app.process_update(update) 
        return func.HttpResponse("OK", status_code=200)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info(f"la funcion /help ha sido invocada")
    try:
        help_text = "Estos son los comandos disponibles:\n"
        help_text += "/start - Iniciar el bot\n"
        help_text += "/comodin - necesito 15 min de agua\n"
        help_text += "/confirmo - confirmo que no tengo fugas\n"
        help_text += "/estado - el estado de la llave, cuantas personas han confirmado tener 0 fugas\n"
        await update.message.reply_text(help_text)
    except Exception as e:
        logging.info(f"ocurrio un error inesperado: {e}")

async def notificar_vecinos(update: Update):
    logging.info("funcion notificar vecinos")
    try:
        text="se ha detectado una fuga, porfavor verifica que no tengas ninguna llave abierta y una vez hecho eso selecciona el comando /confirmo"
        text+="\n si necesitas puedes usar 15 min de uso del agua aunque no hayan confirmado los demas, solo se puede usar una vez.\nPara hacerlo envia el comando /comodin"
        await update.message.reply_text(text)
    except Exception as e:
        logging.info(f"ocurrio un error insesperado: {e}")

async def fuga_detectada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("funcion fuga_detectada ha sido invocada")
    try:
        actualizar_estado_fuga("true")
        user_id = update.message.from_user.id  # Obtener el ID del remitente
        logging.info(f"el usuario {user_id} ha ejecutado el comando fuga")
        bot_id = context.bot.id  # Obtener el ID del admin
        # Si el mensaje lo envió el admin mismo, lo procesamos
        if user_id == int("7572988306"):
            await update.message.reply_text("🚨 Alerta de fuga detectada desde la API.")
            cerrar_llave()
            await notificar_vecinos(update)
        # Si el mensaje lo envió otro usuario
        else:
            await update.message.reply_text("❌ No tienes permiso para ejecutar este comando.")
    except Exception as e:
        logging.info("ocurrio un error insesperado")

async def comodin(update: Update,context: ContextTypes.DEFAULT_TYPE):
    logging.info("funcion comodin ha sido invocada")
    fuga=verificar_fuga() # devuelve tru o false si hay o no fuga
    try:
        if fuga == True:
            user_id = update.message.from_user.id
            respuesta=usar_comodin(user_id)#regresa tru o false dependiendo de si se guardo o no correctamente el valor en la tabla
            if respuesta:
                await update.message.reply_text(f"comodin ingresado por {user_id}, abriendo llave por 15 min")
                abrir_llave(user_id)
            else:
                await update.message.reply_text(f"{user_id} ya has ingresado tu comodin, no puedo abrir llave de nuevo")
        else:
            logging.info("alguien ya ha ingresado el comodin y la llave esta abierta por 15 minutos, comodin no aceptado")
            await update.message.reply_text(f"alguien ya ha ingresado el comodin y la llave esta abierta por 15 minutos, comodin no aceptado")
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")
 

async def confirmacion(update:Update,context: ContextTypes.DEFAULT_TYPE):
    logging.info("funcion confirmacion invocada")
    try:
        if verificar_fuga() == True:
            user_id = update.message.from_user.id # esta linea es lo mismo chat_id = update.message.chat_id
            cont=guardar_confirmacion(str(user_id))#la funcion te regresa el numero de personas faltantes por confirmar
            if cont==2:
                await update.message.reply_text(f"usuario: {user_id} tu confirmacion se ha guardado con exito, todos han confirmado, abriendo llave")
                abrir_llave()#no se envia ningun parametro por que el default es "todos", si es que ya todos han confirmado basado en el contador
                limpiar_datos()
            else:
                await update.message.reply_text(f"usuario: {user_id} tu confirmacion se ha guardado con exito,faltan por confirmar: {cont} ")
        else:
            logging.info("no se ha detectado fuga por tanto no se necesita confirmacion")
            await update.message.reply_text(f"no se ha detectado fuga por tanto no se necesita confirmacion")
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")


async def status(update: Update,context: ContextTypes.DEFAULT_TYPE) -> str:
    logging.info("funcion status ha sido invocada")
    table_client=conectar_storage_account()
    try:
        if estado_de_llave() == "abierta":
            logging.info("el estado de la llave esta abierta, no hay fuga actualmente")
            await update.message.reply_text(f"el estado de la llave esta abierta, no hay fuga actualmente")
        else:
            confirmaciones=obtener_confirmaciones(table_client)
            text=f"el estado actual: hay una fuga, la llave esta cerrada\n"
            text+=f"faltan por confirmar: {confirmaciones} para poder abrir la llave\n"
            await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"hubo un error en la consulta {e}")
        return f"hubo un error en la consulta {e} "

def estado_de_llave()->str:
    logging.info("la funcion estado llave ha sido ejecutada")
    #esta es una logic app que retorna un valor random entre 0 y1 simulando que hacemos una llamada http a la lave inteligente para determinar su estado
    #cuando se compre la llave inteligente se hara como debe de ser
    try:
        response=requests.get(os.environ["logic_app_status"])
        logging.info(response)
        data=response.json()
        message=data["message"]
        if message==0:
            return "cerrada"
        else:
            return "abierta"
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")

def verificar_fuga():
    logging.info("funcion verificar fuga ha sido invocada")
    try:
        table_client=conectar_storage_account()
        entity = table_client.get_entity("estado", "fuga")
        response=entity.get("valor")
        #verifica cual es el estado de la fuga, si es true entonces permite hacer el proceso, sino no hace nada y contesta mensaje
        if response == "true":
            return True
        else: 
            return False
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")
    
def actualizar_estado_fuga(valor:str):
    logging.info("funcion actulizar estado de fuga ha sido invocada")
    try:
        table_client=conectar_storage_account()
        entity = {
                "PartitionKey": "estado",
                "RowKey": "fuga",
                "valor": valor
            }
        table_client.upsert_entity(entity)  # Guarda o actualiza el estado del usuario
        logging.info(f"valor del estado de fuga ha sido atulizado a {valor}")
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")


def conectar_storage_account():
    logging.info("funcion conectar_storage_accout invocada")
    try:
        connection_string=os.environ["CONNECTION_STRING"]
        table_name = "tequis"
        table_service = TableServiceClient.from_connection_string(conn_str=connection_string)
        table_client = table_service.get_table_client(table_name)
        logging.info("conectado a la tabla\n",table_client )
        return table_client
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")



def set_webhook(application:ApplicationBuilder,TOKEN:str):
    #verificar si el webhook esta activado o no 
    try:
        url=f"https://api.telegram.org/bot{TOKEN}/getwebhookinfo"
        response = requests.get(url)
        data = response.json()
        if data["ok"]:
            webhook_info = data["result"]
            if webhook_info["url"]:
                logging.info(f"Webhook está activado en la URL: {webhook_info['url']}")
            else:
                logging.info("No hay un webhook activo.")

                WEBHOOK_URL=os.environ['azure_url']#la url de azure fucntions
                url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}"
                response = requests.get(url)
                if response.status_code == 200:
                    logging.info("✅ Webhook configurado correctamente")
                else:
                    logging.info("❌ Error al configurar webhook:", response.text)
        else:
            logging.info("Error al verificar el estado del webhook.")
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")

def usar_comodin(user_id):
    logging.info("funcion usar_comodin ha sido invocada")
    table_client=conectar_storage_account()
    var=verificar_comodin(user_id,table_client)
    logging.info(f"este es el valro de verificar_comodin : {var} y este el tipo : {type(var)}")
    try:
        if (verificar_comodin(user_id,table_client)) ==  "False":
            entity = {
                "PartitionKey": "confirmaciones",
                "RowKey": str(user_id),
                "comodin": "True"
            }
            table_client.upsert_entity(entity)  # Guarda o actualiza el estado del usuario
            logging.info(f"valor del comodin para el usuario {user_id} ha sido actualizado")
            return(True)
        else:
            logging.info(f"ERROR: usuario={user_id}, tu comodin ya ha sido utilizado")
            return(False)
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")

def verificar_comodin(user_id,table_client):
    logging.info("funcion verificar comodin ha sido invocada")
    try:
        entity = table_client.get_entity("confirmaciones", str(user_id))
        logging.info(entity)
        logging.info("DEBUG 3")
        response=entity.get("comodin")
        logging.info(f"este es el varlo del comodin para el usuario {user_id}, {response}")
        logging.info("DEBUG 4")
        return response #si la entiedad del usuario userId existe, entrega True, sino, entrega False (valor por defecto) si no lo pones puede devolver NOne al no existir el valor
    except Exception as e:
        logging.info(f"ocurrio un error insesperado : {e}")
        return False


def guardar_confirmacion(user_id:str) -> int:
    logging.info("funcion guardar_confirmacion invocada")
    table_client=conectar_storage_account()
    try:
        entity = {
            "PartitionKey": "confirmaciones",
            "RowKey": user_id,
            "confirmado": "True"
        }
        table_client.upsert_entity(entity)  # Guarda o actualiza el estado del usuario
        verificar_confirmacion(user_id,table_client)
        return todos_confirman(table_client)
    except Exception as e:
        logging.info(f"ocurrio un error insesperado: {e}")
        return -10

def verificar_confirmacion(user_id,table_client):
    logging.info("funcion verificar_informacion invocada")
    try:
        entity = table_client.get_entity("confirmaciones", str(user_id))
        return entity.get("confirmado", False)
    except:
        return False

'''
funcion para operar smatr devies TUYA
ACCESS_ID = "tu_client_id"
ACCESS_SECRET = "tu_secret"
DEVICE_ID = "tu_device_id"
REGION = "us"  # Puede ser us, eu, cn, in

def get_token():
    timestamp = str(int(time.time() * 1000))
    sign = hmac.new(
        ACCESS_SECRET.encode(), 
        f"{ACCESS_ID}{timestamp}".encode(), 
        hashlib.sha256
    ).hexdigest().upper()

    url = f"https://openapi.tuya{REGION}.com/v1.0/token?grant_type=1"
    headers = {
        "client_id": ACCESS_ID,
        "sign": sign,
        "t": timestamp,
        "sign_method": "HMAC-SHA256"
    }
    response = requests.get(url, headers=headers)
    return response.json().get("result", {}).get("access_token")


def control_plug(turn_on=True):
    token = get_token()
    url = f"https://openapi.tuya{REGION}.com/v1.0/devices/{DEVICE_ID}/commands"
    headers = {
        "client_id": ACCESS_ID,
        "access_token": token,
        "Content-Type": "application/json"
    }
    payload = {
        "commands": [{"code": "switch_1", "value": turn_on}]
    }
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

'''
def cerrar_llave(user_id:str="todos"):
  if user_id=="todos":
    logging.info(f"se cierra  la llave")
    #aqui creas un http request para cerrar la llave, el http request ira a la llave inteligente
    #pip install pytuya
    # Encender el enchufe
    #logging.info(control_plug(True))
    # Apagar el enchufe
    #logging.info(control_plug(False))
    return "se cierra la llave por fuga detectada"
    

def abrir_llave(user_id:str="todos"):
    logging.info("funcion abrir_llave ha sido invocada, estos son los parametros: ",user_id)
    if user_id=="todos":
        logging.info(f"se abre la llave, ya todos confirmaron")
        return "se abre la llave, ya todos confirmaron"
    else:
        logging.info(f"se abre la llave, el usuario {user_id} ha usado comodin, se cerrara en 15 min")
        #aqui creas una logci app con un delay de 15 minutos  que vuelva a cerrar la llave :p
        logging.info(os.environ['logic_app_15min'])
        try:
            response=requests.get(os.environ["logic_app_15min"])
            data=response.json()
            message=data["message"]
            if response.status_code==200:
                return message
        except Exception as e:
            logging.info(f"algo ocurrio, excepcion: {e}")

def todos_confirman(table_client)-> int:
    logging.info("funcion todos_confirman invocada")
    global vecinos
    logging.info(vecinos)
    cont=0
    try:
        for vecino in vecinos:
            logging.info(f"se esta checando el vecino {vecino}")
            entity = table_client.get_entity("confirmaciones", vecino)
            logging.info("entity: ",entity)
            if entity.get("confirmado", False) == "True":
                cont+=1
        if cont==2:
            logging.info("todos confirmaron")
            limpiar_datos()
            return 2
        else:
            logging.info("aun faltan por confirmar: ",(2-cont))
            return cont        
    except Exception as e:
        return f"excception occured : {e}"
    
def limpiar_datos():
    logging.info("funcion limpiar_datos invocada")
    table_client=conectar_storage_account()
    #vecinos=["vecino1","vecino2","vecino3","vecino4"]#remplazar por userIds
    try:
        global vecinos
        for vecino in vecinos:
            entity = {
                "PartitionKey": "confirmaciones",
                "RowKey": vecino,
                "confirmado": "False",
                "comodin": "False"
            }
            table_client.upsert_entity(entity)  # Guarda o actualiza el estado del usuario
            verificar_confirmacion(vecino,table_client)
            actualizar_estado_fuga("false")
    except Exception as e:
        logging.info(f"ocurrio un error inesperado {e}")


def obtener_confirmaciones(table_client):
    logging.info("funcion obtener confirmaciones ha sido invocada")
    #vecinos=["vecino1","vecino2","vecino3","vecino4"]
    global vecinos
    cont=0
    try:
        for vecino in vecinos:
            entity = table_client.get_entity("confirmaciones", vecino)
            logging.info(f"entity {entity}")
            if entity.get("confirmado", False) == "True":
                logging.info("uno confirmado aumentando contador")
                cont+=1
        logging.info(f"el contador es: {cont}")
        return cont        
    except Exception as e:
        return f"eexecption occured: {e}"


def configurar_bot(application:ApplicationBuilder,TOKEN:str):
    # Configurar manejadores, esto es para ver comandos en los mensajes recibidos
    # Agregar manejador de mensajes desconocidos
    try:
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
        application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Bot trabajando, usa /help para mas comandos.")))
        application.add_handler(CommandHandler("comodin", comodin))
        application.add_handler(CommandHandler("confirmo", confirmacion))
        application.add_handler(CommandHandler("estado", status))
        application.add_handler(CommandHandler("fuga", fuga_detectada))
        set_webhook(application,TOKEN)  # Establece el webhook al iniciar
    except Exception as e:
        logging.info(f"error ocurred: {e}")
    #application.run_polling()  # Reemplaza start_polling() y idle()





try:
    telegram_app = Application.builder().token(TOKEN).build()
    #telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    # Inicializa la Azure Function App
    configurar_bot(telegram_app,TOKEN)
    function_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
    function_app.route("webhook", methods=["POST"])(telegram_webhook)
    #telegram_app = Application.builder().token(TOKEN).build()
except Exception as e:
    logging.info(f"ocurrio un error insesperado : {e}")









