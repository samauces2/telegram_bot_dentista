'''
este codigo crea un bot de telegram y lo configura para ser usado en una azure function
esto hace que la dicho recurso actue como servidor y reduzca costos.
cada vez que alguien interactue con el bot la function se ejecutara y despues de haber hecho lo que se necesita se apagara, pero siempre estara disponible 
NOTA: esto solo sirve para cuando el trafico es muy bajo, ya que entre mas se use la azure function sera mas costosa, considerar el uso de un servidor cuando tu trafico sea muy alto

'''
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext,ContextTypes,ApplicationBuilder
import logging,json,aiohttp,requests
import azure.functions as func
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Updater,ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
#from azure.data.tables import TableServiceClient
#las dos de abajo son para crear botones en las respuestas de los horarios y manejar que hacer con dichos botones
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes

print("🟢 Azure Function cargada correctamente")

'''librerias para google calendar'''
import datetime
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
'''terminan librerias google clanedar'''

#CHECK TODO: terminar la funcion que agrega citas, ya agrega las citas, peor hay que verificar que todos los handlers funcionen correctamente
#TODO: funcion para cancelar cita
#TODO: funcion para cambiar cita
#TODO:

#estados de la conversacion
SELECCION_HORARIO, CONFIRMAR_NOMBRE, INGRESAR_NOMBRE, PREGUNTAR_SERVICIO, SELECCION_SERVICIO = range(5)
INGRESA_CODIGO,REAGENDAR = range(2)

# Servicios y duración en minutos
SERVICIOS = {
    "Limpieza": 30,
    "Revisión": 15,
    "Caries": 60,
    "Otro": 60
}

''' funciones para google calendar'''
# If modifying these scopes, delete the file token.json.
#SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
#use this when creating events
SCOPES = ['https://www.googleapis.com/auth/calendar']


def google_auth():
  print("accediste a la funcion de google_auth")
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if (os.path.exists("token.json")):
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "credentials.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("token.json", "w") as token:
      token.write(creds.to_json())
      #return creds
  return creds
  
def get_events(creds):
    print("accediste a la funcion get_events")
    #creds=google_auth()
    try:
        service = build("calendar", "v3", credentials=creds)
        # Call the Calendar API
        now = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
        print("Getting the upcoming 10 events")
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        opciones = []
        keyboard=[]
        if not events:
            print("No upcoming events found.")
            texto = "no hay citas disponibles\n"
        else:
            # Prints the start and name of the next 10 events
            for i,event in enumerate(events):
                if "Disponible" in event.get("summary", ""):  # filtramos los bloques disponibles
                    start = event["start"].get("dateTime", event["start"].get("date"))
                    print(start, event["summary"])
                    hora = datetime.datetime.fromisoformat(start).strftime("%d-%m-%Y %H:%M")
                    opciones.append(hora)
                    keyboard.append([InlineKeyboardButton(hora, callback_data=hora)])
            if opciones:
                texto = "Estos son los espacios disponibles:\n"
                texto += "\n".join(f"{i+1}. {opt}" for i, opt in enumerate(opciones))
                texto += "\n\nResponde con el número de la opción que deseas."
                return InlineKeyboardMarkup(keyboard)
                #await update.message.reply_text(texto)
                # Aquí podrías guardar el estado para saber que estás esperando respuesta
    except HttpError as error:
        print(f"An error occurred: {error}")
    #return InlineKeyboardMarkup(keyboard)

def crear_evento(creds, nombre_paciente, fecha_hora_str,duracion):
    try:
        service = build("calendar", "v3", credentials=creds)
        # Parsear la fecha y hora de string tipo '19-06 11:30'
        fecha = datetime.datetime.strptime(fecha_hora_str, "%d-%m-%Y %H:%M")
        print("esta es la fecha:",fecha)
        fecha_utc = fecha.astimezone(datetime.timezone.utc)
        print("esta es la fecha_utc:",fecha_utc)
        fecha_fin = fecha_utc + datetime.timedelta(minutes=duracion)
        print("esta es la fecha fin:",fecha_fin)
        print("esta es la fechautciso format:",fecha_utc.isoformat())
        eventos_existentes = service.events().list(
            calendarId='primary',
            timeMin=fecha_utc.isoformat(),
            timeMax=fecha_fin.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        for event in eventos_existentes.get('items', []):
            if 'Cita con' in event.get('summary', ''):
                print(f"⚠️ Ya existe una cita en ese horario: {event['summary']}")
                return False, "Ya hay una cita registrada en ese horario."
        for event in eventos_existentes.get('items', []):
            if 'Disponible' in event.get('summary', ''):
                # Editamos el evento "Disponible"
                event['summary'] = f'Cita con {nombre_paciente}'
                event['description'] = f'Cita dental agendada por el bot con {nombre_paciente}'
                event['start']['dateTime'] = fecha_utc.isoformat()
                event['end']['dateTime'] = fecha_fin.isoformat()
                updated_event = service.events().update(
                    calendarId='primary',
                    eventId=event['id'],
                    body=event
                ).execute()
                print(f"✅ Evento actualizado: {updated_event.get('htmlLink')}")
                return True, None
    except HttpError as error:
        print(f"❌ Error al crear el evento: {error}")
        return False, "Error al acceder a Google Calendar."

'''terminan funciones para google calendar'''

'''
handlers para el bot de telegram
'''

async def ingresa_codigo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("accediste a la funcion ingresa_codigo")
    message = update.message
    codigo = message.text.strip()  # Obtener el código ingresado por el usuario
    print(f"Código ingresado: {codigo}")
    # Aquí puedes agregar lógica para verificar el código
    if int(codigo) :  # Ejemplo de verificación simple
        await message.reply_text("Código correcto. ¿Quieres reagendar tu cita?")
        keyboard = [
            [InlineKeyboardButton("Sí", callback_data="reagendar_cita")],
            [InlineKeyboardButton("No", callback_data="terminar")]
        ]
        await message.reply_text("Selecciona una opción:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REAGENDAR
    else:
        await message.reply_text("Código incorrecto. Inténtalo de nuevo.")
        return INGRESA_CODIGO
    
async def reagendar_cita(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("accediste a la funcion reagendar_cita")
    query = update.callback_query
    await query.answer()
    if query.data != "reagendar_cita":
        await query.edit_message_text("Operación cancelada.")
        return ConversationHandler.END
    # Aquí puedes agregar lógica para reagendar la cita
    await query.edit_message_text("Por favor, selecciona un nuevo horario para tu cita:")
    creds = google_auth()
    events = get_events(creds)
    if isinstance(events, InlineKeyboardMarkup):
        await query.edit_message_reply_markup(reply_markup=events)
        return SELECCION_HORARIO
    else:
        await query.edit_message_text("No hay horarios disponibles en este momento.")
        return ConversationHandler.END

async def handle_cita_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cita = query.data  # ejemplo: "cita_0", "cita_1", etc.
    user = update.effective_user #query.from_user
    nombre = f"{user.first_name or ''} {user.last_name or ''}".strip()
    usuario = user.username or 'sin username'
    user_id = user.id
    print(f"Nombre: {nombre}, Usuario: @{usuario}, ID: {user_id}")
    #await query.edit_message_text(
    #f"✅ ¡Tu cita para el {seleccion} ha sido registrada a nombre de: {nombre}!")
    # Aquí puedes mapear el índice al evento real si lo necesitas
    # Guarda la cita y nombre por si el usuario quiere cambiarlo después
    context.user_data["cita"] = cita
    context.user_data["nombre_telegram"] = nombre
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sí", callback_data="nombre_correcto"),
            InlineKeyboardButton("❌ No", callback_data="nombre_incorrecto")
        ]
    ])

    await query.edit_message_text(
        f"¿Tu nombre es: *{nombre}*?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

async def handle_nombre_confirmacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    respuesta = query.data
    if respuesta == "nombre_correcto":
        nombre = context.user_data.get("nombre_telegram", "Nombre desconocido")
        cita = context.user_data.get("cita", "sin cita")
        #TODO: agregar la funcion que creara el evento en google calendar
        creds = google_auth()
        exito, mensaje_error = crear_evento(creds, nombre, cita)
        if exito:
            await query.edit_message_text(
                f"✅ Cita confirmada para *{nombre}* el *{cita}*.\nHa sido añadida a la agenda.",
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text(
                f"❌ Ocurrió un error al guardar la cita en Google Calendar: {mensaje_error}",
                parse_mode="Markdown"
            )
        # Aquí puedes guardar el evento o enviarlo al dentista
    elif respuesta == "nombre_incorrecto":
        await query.edit_message_text("Por favor, escribe tu nombre completo:")
        context.user_data["esperando_nombre"] = True

async def handle_nombre_personalizado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("esperando_nombre"):
        nombre = update.message.text
        cita = context.user_data.get("cita", "sin cita")
        context.user_data["nombre_personalizado"] = nombre
        context.user_data["esperando_nombre"] = False
        creds = google_auth()
        exito , mensaje_error= crear_evento(creds, nombre, cita)
        if exito:
            await update.message.reply_text(
                f"✅ Cita confirmada para *{nombre}* el *{cita}*.\nHa sido añadida a la agenda.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ Ocurrió un error al guardar la cita en Google Calendar {mensaje_error}",
                parse_mode="Markdown"
            )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Lo siento, no entiendo ese comando. Usa /ayuda para ver las opciones disponibles, recuerda usar '/' antes de la palabra")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = "Estos son los comandos disponibles:\n"
    help_text += "/start - Iniciar el bot\n"
    help_text += "/agendar_cita - quiero agendar una cita\n"
    help_text += "/confirmar_cita - confirmo mi asitencia a la cita\n"
    help_text += "/cancelar_cita - cancelar mi cita, nuevas opciones para cita apareceran\n"
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
    #await update.message.reply_text("tu cita se ha cancelado con exito")
    await update.message.reply_text(text="ingresa tu codigo de cita")
    return INGRESA_CODIGO
    #return

async def agendar_cita(update:Update,context: ContextTypes.DEFAULT_TYPE):
    print("funcion agendar_cita invocada")
    user_id = update.message.from_user.id # esta linea es lo mismo chat_id = update.message.chat_id
    #await update.message.reply_text(f"usuario: {user_id} tu confirmacion se ha guardado con exito,faltan por confirmar: {cont} ")
    #TODO: agregar codigo borrar la cita de la agenda y preguntar si quiere volver a agendar cita
    #texto=await get_events()
    #await google_auth()
    creds=google_auth()
    events=get_events(creds)
    #await update.message.reply_text("tu cita se ha agendado con exito")
    await update.message.reply_text(text="horarios disponibles",reply_markup=events)
    return SELECCION_HORARIO

async def seleccionar_horario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("accediste a la funcion pseleccionar horario")
    query = update.callback_query
    await query.answer()
    context.user_data['fecha'] = query.data

    user = update.effective_user
    nombre = f"{user.first_name or ''} {user.last_name or ''}".strip()
    context.user_data['nombre'] = nombre

    keyboard = [
        [InlineKeyboardButton("Sí", callback_data="nombre_ok"),
         InlineKeyboardButton("No", callback_data="nombre_no")]
    ]
    await query.edit_message_text(f"¿Tu nombre es: {nombre}?", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRMAR_NOMBRE

async def confirmar_nombre(update:Update, context: ContextTypes.DEFAULT_TYPE):
    print("accediste a la funcion confirmar nombre")
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton(s, callback_data=s)] for s in SERVICIOS]
    if query.data == "nombre_ok":
        print("el usuario confirmo su nombre")
        #return await preguntar_servicio(query, context)
        #if isinstance(update, Update):
        await query.edit_message_text("¿Qué servicio necesitas?", reply_markup=InlineKeyboardMarkup(keyboard))
        #else:
        #    await query.edit_message_text("¿Qué servicio necesitas?", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECCION_SERVICIO
    else:
        print("el usuario no confirmo su nombre")
        await query.edit_message_text("Por favor escribe tu nombre completo:")
        print("debug1")
        return INGRESAR_NOMBRE

async def ingresar_nombre(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("accediste a la funcion ingresar nombre")
    message = update.message
    nombre=message.text.strip()#to remove whitespaes from the beggining and ending of the string
    #nombre = update.message.text.strip()
    print("el nombre del usuario: ",nombre)
    context.user_data['nombre'] = nombre
    keyboard = [[InlineKeyboardButton(s, callback_data=s)] for s in SERVICIOS]
    await message.reply_text("¿Qué servicio necesitas?", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECCION_SERVICIO

#async def preguntar_servicio(update:Update, context: ContextTypes.DEFAULT_TYPE):
#    print("accediste a la funcion preguntar servicio")
#    
#    return SELECCION_SERVICIO

async def seleccionar_servicio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("accediste a la funcion seleccionar servicio")
    query = update.callback_query
    await query.answer()
    servicio = query.data
    context.user_data['servicio'] = servicio

    nombre = context.user_data['nombre']
    fecha = context.user_data['fecha']
    duracion = SERVICIOS.get(servicio, 30)

    creds = google_auth()
    #crear_evento(creds, nombre_paciente, fecha_hora_str)
    exito, info = crear_evento(creds, nombre, fecha, duracion)
    if exito:
        await query.edit_message_text(f"✅ Cita confirmada para {nombre} el {fecha} por servicio de {servicio}.")
    else:
        await query.edit_message_text(f"❌ No se pudo agendar la cita: {info}")
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cita cancelada.")
    return ConversationHandler.END


async def echo(update: Update, context: CallbackContext) -> None:
    """Responde repitiendo el mensaje del usuario."""
    await update.message.reply_text(update.message.text)
    


def configurar_bot(application:ApplicationBuilder,TOKEN:str):
    print("accediste a la funcion configurar bot")
    # Configurar manejadores, esto es para ver comandos en los mensajes recibidos
    # Agregar manejador de mensajes desconocidos
    set_webhook(application,TOKEN)  # Establece el webhook al iniciar
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("agendar_cita", agendar_cita)],
        states={
            SELECCION_HORARIO: [CallbackQueryHandler(seleccionar_horario)],
            CONFIRMAR_NOMBRE: [CallbackQueryHandler(confirmar_nombre)],
            INGRESAR_NOMBRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingresar_nombre)],
            #PREGUNTAR_SERVICIO: [CallbackQueryHandler(preguntar_servicio)],  
            SELECCION_SERVICIO: [CallbackQueryHandler(seleccionar_servicio)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    conv_handler_cancel = ConversationHandler(
        entry_points=[CommandHandler("cancelar_cita", cancelar_cita)],
        states={
            INGRESA_CODIGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingresa_codigo)],
            REAGENDAR: [CallbackQueryHandler(reagendar_cita)]
            #PREGUNTAR_SERVICIO: [CallbackQueryHandler(preguntar_servicio)],  
            #SELECCION_SERVICIO: [CallbackQueryHandler(seleccionar_servicio)]
        },
        fallbacks=[CommandHandler("cancelar", cancelar)]
    )
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(conv_handler)
    application.add_handler(conv_handler_cancel)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    application.add_handler(CommandHandler("start", lambda update, context: update.message.reply_text("Bot trabajando, usa /help para mas comandos.")))
    application.add_handler(CommandHandler("confirmar_cita", confirmacion))
    #application.add_handler(CommandHandler("cancelar_cita", cancelar_cita))
    #application.add_handler(CommandHandler("agendar_cita", agendar_cita))
    
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

#app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
# Token del bot (reemplázalo con tu propio token)
#TOKEN=""#agrega tu token del bot de telegram aqui
#ngrok_url=""#agrega tu URL de ngrok o de azure functions, cada vez que ejecutes ngrok tienes que eliminar el viejo webhook
#asi : https://api.telegram.org/bot<TOKEN>/deleteWebhook



telegram_app = Application.builder().token(TOKEN).build()



#telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
# Inicializa la Azure Function App
configurar_bot(telegram_app,TOKEN)
function_app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)
function_app.route("webhook", methods=["POST"])(telegram_webhook)






