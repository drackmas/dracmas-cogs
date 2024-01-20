# Import necessary modules
import aiml

# Create a Chatbot instance
chatbot = aiml.Kernel()

# Load AIML files
chatbot.learn("std-startup.xml")
chatbot.respond("load aiml b")

# Define a function to get chatbot response
def get_response(message):
    return chatbot.respond(message)
