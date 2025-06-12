'''
este codigo crea un bot de telegram y lo configura para ser usado en una azure function
esto hace que la dicho recurso actue como servidor y reduzca costos.
cada vez que alguien interactue con el bot la function se ejecutara y despues de haber hecho lo que se necesita se apagara, pero siempre estara disponible 
NOTA: esto solo sirve para cuando el trafico es muy bajo, ya que entre mas se use la azure function sera mas costosa, considerar el uso de un servidor cuando tu trafico sea muy alto

'''
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext,ContextTypes,ApplicationBuilder
print("test")
import logging,json,aiohttp,requests
import azure.functions as func
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater,ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from azure.data.tables import TableServiceClient
#vecinos=["123123312","123132132"] # id de telegram de los vecinos
print("🟢 Azure Function cargada correctamente")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Lo siento, no entiendo ese comando. Usa /ayuda para ver las opciones disponibles, recuerda usar '/' antes de la palabra")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "Estos son los comandos disponibles:\n"
    help_text += "/start - Iniciar el bot\n"
    help_text += "/agendar_cita - quiero agendar una cita\n"
    help_text += "/confirmar_cita - confirmo mi asitencia a la cita\n"
    #help_text += "/estado - el estado de la llave, cuantas personas han confirmado tener 0 fugas\n"
    await update.message.reply_text(help_text)

async def confirmacion(update:Update,context: ContextTypes.DEFAULT_TYPE):
    print("funcion confirmacion invocada")
    user_id = update.message.from_user.id # esta linea es lo mismo chat_id = update.message.chat_id
    #await update.message.reply_text(f"usuario: {user_id} tu confirmacion se ha guardado con exito,faltan por confirmar: {cont} ")
    #TODO: agregar codigo para que la cita se marque como confirmada
    await update.message.reply_text("tu cita se ha agendado con exito")
    return

async def cancelar_cita(update:Update,context: ContextTypes.DEFAULT_TYPE):
    print("funcion cancelar_cita invocada")
    user_id = update.message.from_user.id # esta linea es lo mismo chat_id = update.message.chat_id
    #await update.message.reply_text(f"usuario: {user_id} tu confirmacion se ha guardado con exito,faltan por confirmar: {cont} ")
    #TODO: agregar codigo borrar la cita de la agenda y preguntar si quiere volver a agendar cita
    await update.message.reply_text("tu cita se ha cancelado con exito")
    return

async def agendar_cita(update:Update,context: ContextTypes.DEFAULT_TYPE):
    print("funcion agendar_cita invocada")
    user_id = update.message.from_user.id # esta linea es lo mismo chat_id = update.message.chat_id
    #await update.message.reply_text(f"usuario: {user_id} tu confirmacion se ha guardado con exito,faltan por confirmar: {cont} ")
    #TODO: agregar codigo borrar la cita de la agenda y preguntar si quiere volver a agendar cita
    await update.message.reply_text("tu cita se ha agendado con exito")
    return

async def echo(update: Update, context: CallbackContext) -> None:
    """Responde repitiendo el mensaje del usuario."""
    await update.message.reply_text(update.message.text)
    


def configurar_bot(application:ApplicationBuilder,TOKEN:str):
    print("accediste a la funcion configurar bot")
    # Configurar manejadores, esto es para ver comandos en los mensajes recibidos
    # Agregar manejador de mensajes desconocidos
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Bot trabajando, usa /help para mas comandos.")))
    application.add_handler(CommandHandler("confirmar_cita", confirmacion))
    application.add_handler(CommandHandler("cancelar_cita", cancelar_cita))
    application.add_handler(CommandHandler("agendar_cita", agendar_cita))
    set_webhook(application,TOKEN)  # Establece el webhook al iniciar
    # Ejecuta el bot
    #application.run_polling()  # Reemplaza start_polling() y idle()

def set_webhook(application:ApplicationBuilder,TOKEN:str):
    #verificar si el webhook esta activado o no 
    url=f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
    print(url)
    response = requests.get(url)
    print(f"este es la respuesta: {response}")
    data=response.json()
    if data["ok"]:
        webhook_info = data["result"]
        if webhook_info["url"]:
            print(f"Webhook está activado en la URL: {webhook_info['url']}")
        else:
            print("No hay un webhook activo.")
            WEBHOOK_URL=f"{ngrok_url}/api/webhook"#la url de azure fucntions o ngrok
            url = f"https://api.telegram.org/bot{TOKEN}/setWebhook?url={WEBHOOK_URL}"
            response = requests.get(url)
            if response.status_code == 200:
                print("✅ Webhook configurado correctamente")
            else:
                print("❌ Error al configurar webhook:", response.text)
    else:
        print("Error al verificar el estado del webhook.")





# Función de manejo de solicitudes HTTP para Azure Functions
async def telegram_webhook(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data=req.get_json()
        print(data)
        if not telegram_app.bot:  # Verificar si el bot no está inicializado
            print("no inicio")
            await telegram_app.initialize()  # Inicializar el bot antes de procesar la actualización
        update = Update.de_json(data, telegram_app.bot)
        print("debug")
        await telegram_app.initialize()
        await telegram_app.process_update(update)  # Ahora usamos await directamente
        return func.HttpResponse("OK", status_code=200)
    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return func.HttpResponse(f"Error: {str(e)}", status_code=500)

# Activa el logging para depuración
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=print)

print("tesssssst")
#app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
# Token del bot (reemplázalo con tu propio token)
TOKEN=""#agrega tu token del bot de telegram aqui
ngrok_url=""#agrega tu URL de ngrok o de azure functions, cada vez que ejecutes ngrok tienes que eliminar el viejo webhook
#asi : https://api.telegram.org/bot<TOKEN>/deleteWebhook


telegram_app = Application.builder().token(TOKEN).build()
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

# Inicializa la Azure Function App
configurar_bot(telegram_app,TOKEN)
function_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
function_app.route("webhook", methods=["POST"])(telegram_webhook)






