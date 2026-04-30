import random
import logging
import asyncio
from opcua_server import OPCServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def simulate_tag_changes(server: OPCServer, duration: int = 60, interval: int = 3):
    """
    Simula il cambiamento periodico dei tag per testare la subscription del client.
    
    Questa funzione simula uno scenario di macchina con cicli che cambiano lo stato
    dei tag durante l'esecuzione.
    
    Args:
        duration: Durata totale della simulazione in secondi (default: 60)
        interval: Intervallo di tempo tra i cambiamenti dei tag in secondi (default: 5)
    """

    start_time = asyncio.get_event_loop().time()
    cycle_count = 0
    
    try:
        while (asyncio.get_event_loop().time() - start_time) < duration:
            cycle_count += 1
            
            # Simulazione con probabilità: cambiamento di stato casuale
            # Probabilità che la macchina sia in ciclo (60%)
            if random.random() < 0.6:
                await server.set_tag_value("InCycle", True)
                await server.set_tag_value("InBypass", False)
            else:
                await server.set_tag_value("InCycle", False)
                await server.set_tag_value("InBypass", True)
            
            # Probabilità di warning (20%)
            if random.random() < 0.2:
                await server.set_tag_value("InWarning", True)
            else:
                await server.set_tag_value("InWarning", False)
            
            # Probabilità di allarme (20%)
            if random.random() < 0.2:
                await server.set_tag_value("InAlarm", True)
            else:
                await server.set_tag_value("InAlarm", False)
            
            await server.print_tag_status()
            
            await asyncio.sleep(interval)  # Wait for the next cycle
    
    except asyncio.CancelledError:
        logger.info("Simulazione interrotta dall'utente")
    except Exception as e:
        logger.error(f"Errore durante la simulazione: {e}")


async def main():
    """Funzione principale per avviare il server e la simulazione."""
    # Crea l'istanza del server
    opc_server = OPCServer(endpoint="opc.tcp://0.0.0.0:4840/freeopcua/server/")
    await opc_server.setup()
    
    server_task = asyncio.create_task(opc_server.start())  # Start the server in background
    
    # Avvia la simulazione dei tag con durata limitata (60 secondi)
    simulation_task = asyncio.create_task(
        simulate_tag_changes(opc_server, duration=60, interval=3)
    )
    
    try:
        # Attendi il completamento della simulazione
        await simulation_task
        logger.info("Simulazione completata")
    except KeyboardInterrupt:
        logger.info("Interruzione ricevuta")
    finally:
        # Ferma il server
        server_task.cancel()
        await opc_server.stop()


if __name__ == "__main__":
    asyncio.run(main())
