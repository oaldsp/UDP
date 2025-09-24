import socket
import os
import hashlib
import time

HOST = '127.0.0.1'  # Endereço IP do servidor (localhost)
PORT = 9999         # Porta para operar
BUFFER_SIZE = 1024  # Tamanho do payload de dados
FILE_DIR = "files"  # Diretório onde os arquivos a serem enviados estão localizados
HEADER_SIZE = 21 
#    4 bytes (Número da Sequência) 
# + 16 bytes (CHECKSUM - MD5) 
# +  1 byte  (Flag de Fim)
PAYLOAD_SIZE = BUFFER_SIZE - HEADER_SIZE

def calculate_md5(data):
    #Calcula o checksum MD5.
    md5 = hashlib.md5()#Instancia o objeto MD5
    md5.update(data)#Calcula o hash do dado
    return md5.digest()

def sepate_segments(filepath):
    segments = []#Lista de Tuplas (seq_num, data)

    with open(filepath, 'rb') as f:
        seq_num = 0
        while True:
            data = f.read(PAYLOAD_SIZE)
            if not data:
                break
            
            segments.append((seq_num, data))
            seq_num += 1
    
    print(f"[*] Arquivo dividido em {seq_num} segmentos.")

    return segments, seq_num

def send_file(server_socket, client_address, filepath, file_segments_cache):

    segments, total_segments = sepate_segments(filepath)
    
    file_segments_cache[client_address] = segments
    
    # Envia cada segmento
    for i, (seq_num, data) in enumerate(segments):
        is_last_segment = (i == total_segments - 1)
        
        # Monta o cabeçalho
        seq_num_bytes = seq_num.to_bytes(4, 'big')
        checksum = calculate_md5(data)
        eof_flag = (1).to_bytes(1, 'big') if is_last_segment else (0).to_bytes(1, 'big')
        
        header = seq_num_bytes + checksum + eof_flag
        packet = header + data
        
        server_socket.sendto(packet, client_address)
        print(f"    -> Enviando segmento {seq_num}/{total_segments - 1}", end='\r')
        time.sleep(0.0001)

    print(f"\n[*] Transferência de para {client_address} concluída.")

def get(server_socket, client_address, filename, file_segments_cache):
    filepath = os.path.join(FILE_DIR, filename)

    if os.path.exists(filepath):
        print(f"[*] Arquivo '{filename}' encontrado. Iniciando transferência.")
        send_file(server_socket, client_address, filepath, file_segments_cache)
    else:
        error_message = "ERROR: Arquivo nao encontrado".encode('utf-8')
        server_socket.sendto(error_message, client_address)
        print(f"[!] Erro: Arquivo '{filename}' não encontrado. Mensagem de erro enviada.")

def retransmit(server_socket, client_address, missing_seq_nums, file_segments_cache):            
    print(f"[*] Recebida solicitação de retransmissão para os segmentos: {missing_seq_nums}")
                
    if client_address in file_segments_cache:
        segments_to_resend = file_segments_cache[client_address]
        total_segments = len(segments_to_resend)
        
        for seq_num in missing_seq_nums:
            if seq_num < len(segments_to_resend):
                _, data = segments_to_resend[seq_num]
                is_last_segment = (seq_num == total_segments - 1)

                # Remonta o pacote e reenvia
                seq_num_bytes = seq_num.to_bytes(4, 'big')
                checksum = calculate_md5(data)
                eof_flag = (1).to_bytes(1, 'big') if is_last_segment else (0).to_bytes(1, 'big')
                
                header = seq_num_bytes + checksum + eof_flag
                packet = header + data
                
                server_socket.sendto(packet, client_address)
                print(f"    -> Reenviando segmento {seq_num}")
    else:
        print(f"[*] Arquivo solicitado não encontrado. Nenhum segmento para retransmitir.")

def main():
    if not os.path.exists(FILE_DIR):
        os.makedirs(FILE_DIR)

    # Criando o socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # AF_INET    => IPv4
    # SOCK_DGRAM => UDP
    
    # Vincula o socket ao endereço e porta especificados
    server_socket.bind((HOST, PORT))
    print(f"[*] Servidor UDP escutando em {HOST}:{PORT}")

    file_segments_cache = {} # Armazena os segmentos em cache para possível retransmissão

    while True:
        try:
            request, client_address = server_socket.recvfrom(BUFFER_SIZE)# Aguarda por uma requisição do cliente, no maximo tamanho BUFFER_SIZE
            request_str = request.decode('utf-8')
            print(f"\n[+] Recebida requisição de {client_address}: {request_str}")

            if request_str.startswith("GET /"):
                filename = request_str.split(" ")[1].strip("/")
                get(server_socket, client_address, filename, file_segments_cache)
            
            # --- Lógica de Retransmissão ---
            elif request_str.startswith("RETRANSMIT:"):
                missing_seq_nums_str = request_str.split(":")[1]
                missing_seq_nums = [int(n) for n in missing_seq_nums_str.split(',') if n]

                retransmit(server_socket, client_address, missing_seq_nums, file_segments_cache)

        except Exception as e:
            print(f"[!] Ocorreu um erro: {e}")

if __name__ == "__main__":
    main()