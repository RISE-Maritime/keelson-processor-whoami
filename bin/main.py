import zenoh
from zenoh import QueryTarget
import logging
import warnings
import atexit
import json
import time
import keelson
from terminal_inputs import terminal_inputs
from keelson.payloads.NetworkPing_pb2 import NetworkPing

session = None
args = None


def query_ping(query):
    """
    Query for testing the network connection

    - Loop time of the message should be measured 

    Args:
        query (zenoh.Query): Zenoh query object
    Returns:
        envelope (bytes) with compressed payload
    """
    
    query_key = query.selector
    logging.debug(f">> [Query Ping] Received key: {query_key}")

    query_payload = query.value
    logging.debug(f">> [Query Ping] Received payload: {query_payload}")


    query.reply(zenoh.Sample(str(query.selector), query_payload)) # Send the reply on same key as the query





def query_ping_upload_and_download(query):
    """
    Query for testing the network connection
     
      -  Loping the message payload back to sender with timestamp 

    Args:
        query (zenoh.Query): Zenoh query object
    Returns:
        envelope (bytes) with compressed payload
    """

    ingress_timestamp = time.time_ns()
    
    query_key = query.selector
    logging.debug(f">> [Query] Received query key {query_key}")

    query_payload = query.value.payload
    # logging.debug(f">> [Query] Received query payload {query_payload}")

    received_at, enclosed_at, content = keelson.uncover(query_payload)
    message_received = NetworkPing.FromString(content)

    # logging.debug(message_received.timestamp_sender)
  
    # Re-Packing with new timestamp and ping count
    payload = NetworkPing()
    payload.timestamp_sender.FromNanoseconds(message_received.timestamp_sender.ToNanoseconds())
    payload.timestamp_receiver.FromNanoseconds(ingress_timestamp)
    payload.id_sender = message_received.id_sender
    payload.id_receiver = args.entity_id
    payload.ping_count = message_received.ping_count + 1
    payload.payload_description = message_received.payload_description
    payload.payload_size_mb = message_received.payload_size_mb
    payload.payload_size_bytes = message_received.payload_size_bytes
    payload.dummy_payload = message_received.dummy_payload 
    serialized_payload = payload.SerializeToString()
    envelope = keelson.enclose(serialized_payload)

    query.reply(zenoh.Sample(str(query.selector), envelope)) # Send the reply on same key as the query




def subscriber_camera_publisher(data):
    """
    Subscriber trigger by camera image incoming
    """

    ingress_timestamp = time.time_ns()
    
    data_key = data.selector
    logging.debug(f">> [Query] Received query key {data_key}")

    data_payload = data.value.payload
    logging.debug(f">> [Query] Received query payload {data_payload}")

    received_at, enclosed_at, content = keelson.uncover(data_payload)
    logging.debug(f"content {content} received_at: {received_at}, enclosed_at {enclosed_at}")
    Image = CompressedImage.FromString(content)
    img_dic = {
            "timestamp": Image.timestamp.ToDatetime(),
            "frame_id": Image.frame_id,
            "data": Image.data,
            "format": Image.format
        }
    

    ##########################
    # TODO: STITCHING HERE
    ##########################


    # Packing panorama created
    newImage = CompressedImage()
    newImage.timestamp.FromNanoseconds(ingress_timestamp)
    newImage.frame_id = "foxglove_frame_id"
    newImage.data = b"binary_image_data" # Binary image data 
    newImage.format = "jpeg" # supported formats `webp`, `jpeg`, `png`
    serialized_payload = newImage.SerializeToString()
    envelope = keelson.enclose(serialized_payload)
    pub_camera_panorama.put(envelope)


def fixed_hz_publisher():

    ingress_timestamp = time.time_ns()

    # Camera image getter
    replies = session.get(
        args.camera_query,
        zenoh.Queue(),
        target=QueryTarget.BEST_MATCHING(),
        consolidation=zenoh.QueryConsolidation.NONE(),
    )


    for reply in replies.receiver:
        try:
            print(
                ">> Received ('{}': '{}')".format(reply.ok.key_expr, reply.ok.payload)
            )
            # Unpacking image    
            received_at, enclosed_at, content = keelson.uncover(reply.ok.payload)
            logging.debug(f"content {content} received_at: {received_at}, enclosed_at {enclosed_at}")
            Image = CompressedImage.FromString(content)

            img_dic = {
                "timestamp": Image.timestamp.ToDatetime(),
                "frame_id": Image.frame_id,
                "data": Image.data,
                "format": Image.format
            }

        except:
            print(">> Received (ERROR: '{}')".format(reply.err.payload))

    ##########################
    # TODO: STITCHING HERE
    ##########################


    # Packing panorama created
    newImage = CompressedImage()
    newImage.timestamp.FromNanoseconds(ingress_timestamp)
    newImage.frame_id = "foxglove_frame_id"
    newImage.data = b"binary_image_data" # Binary image data 
    newImage.format = "jpeg" # supported formats `webp`, `jpeg`, `png`
    serialized_payload = newImage.SerializeToString()
    envelope = keelson.enclose(serialized_payload)
    pub_camera_panorama.put(envelope)
    time.sleep(1 / args.fixed_hz)




if __name__ == "__main__":
    # Input arguments and configurations
    args = terminal_inputs()
    # Setup logger
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s", level=args.log_level
    )
    logging.captureWarnings(True)
    warnings.filterwarnings("once")

    ## Construct session
    logging.info("Opening Zenoh session...")
    conf = zenoh.Config()
    if args.connect is not None:
        conf.insert_json5(zenoh.config.CONNECT_KEY, json.dumps(args.connect))
    session = zenoh.open(conf)

    def _on_exit():
        session.close()

    atexit.register(_on_exit)
    logging.info(f"Zenoh session established: {session.info()}")

    #################################################
    # Setting up QUERYABLE´s

    # Ping test queryable
    key_exp_query_ping = keelson.construct_req_rep_key(
        realm=args.realm,
        entity_id=args.entity_id,
        responder_id="network",
        procedure="ping",
    )
    query_network_ping = session.declare_queryable(
        key_exp_query_ping,
        query_ping
    )
    logging.info(f"Created queryable: {key_exp_query_ping}")

    # Ping test up and down load queryable
    key_exp_query_ping_up_down = keelson.construct_req_rep_key(
        realm=args.realm,
        entity_id=args.entity_id,
        responder_id="network",
        procedure="ping_up_down",
    )
    query_network_ping_up_down = session.declare_queryable(
        key_exp_query_ping_up_down,
        query_ping_upload_and_download
    )
    logging.info(f"Created queryable: {key_exp_query_ping_up_down}")


    #################################################
    # Setting up PUBLISHER´s 

    # Network ping result publisher
    key_exp_pub_results = keelson.construct_pub_sub_key(
        realm=args.realm,
        entity_id=args.entity_id,
        subject="network_ping",  # Needs to be a supported subject
        source_id="results" ,
    )
    pub_camera_panorama = session.declare_publisher(
        key_exp_pub_results,
        priority=zenoh.Priority.INTERACTIVE_HIGH(),
        congestion_control=zenoh.CongestionControl.DROP(),
    )
    logging.info(f"Created publisher: {key_exp_pub_results}")


    #################################################

    try:
   
           
        if args.trigger == "ping":
            logging.info("Trigger Ping")
            while True:
                for platform in args.ping_common_key:
                    timestamp_init = time.time_ns()
                    for reply in session.get(platform + "/rpc/network/ping", zenoh.Queue(), value=None):
                        try:
                            timestamp_received = time.time_ns()
                            time_diff = (timestamp_received - timestamp_init) / 1000000
                            logging.debug(f"TIME DIFF: {time_diff} ms")
                            logging.debug(f"Received '{reply.ok.key_expr}': '{reply.ok.payload.decode('utf-8')}'")
                        except:
                            logging.debug(f"Received ERROR: '{reply.err.payload.decode('utf-8')}'")
                time.sleep(1)


        elif args.trigger == "ping_up_down":
            logging.info("Trigger Ping Up and Down")
       
            for platform in args.ping_common_key:
                
                mb = args.start_mb
                count = 0

                while mb <= args.end_mb:
                    timestamp_init = time.time_ns()

                    size_in_bytes = mb * 1024 * 1024
                    dummy_payload = bytes(bytearray(int(size_in_bytes)))

                    payload = NetworkPing()
                    payload.timestamp_sender.FromNanoseconds(timestamp_init)
                    payload.id_sender = args.entity_id
                    payload.id_receiver = platform.split("/")[-1]
                    payload.ping_count = count
                    payload.payload_description = "Ping test upp and down"
                    payload.payload_size_mb = mb
                    payload.payload_size_bytes = size_in_bytes                   
                    payload.dummy_payload = dummy_payload

                    serialized_payload = payload.SerializeToString()
                    envelope = keelson.enclose(serialized_payload)

                    for reply in session.get(platform + "/rpc/network/ping_up_down", zenoh.Queue(), value=envelope):
                        try:
                            timestamp_received = time.time_ns()
                            time_diff = (timestamp_received - timestamp_init) / 1000000
                            logging.debug(f"TIME DIFF ({mb} MB): {time_diff} ms  '{reply.ok.key_expr}' ")
                        except:
                            logging.debug(f"Received ERROR: '{reply.err.payload.decode('utf-8')}'")

                    count += 1
                    mb += args.step_mb 
                    # END OF LOOP

                       

            
                    


                    
                time.sleep(1)






        else: 
            logging.info("No trigger specified, waiting for queries...")
            logging.info("Ctrl-C / Ctrl-Z to exit.")

            while True:
                time.sleep(1)
                    





    except KeyboardInterrupt:
        logging.info("Program ended due to user request (Ctrl-C)")
    except Exception as e:
        logging.error(f"Program ended due to error: {e}")
    finally:
        logging.info("Closing Zenoh session...")
        session.close()
        logging.info("Zenoh session closed.")
