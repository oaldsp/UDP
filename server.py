# server.py

import socket
import os
import hashlib
import time

# --- Configurações do Servidor ---
HOST = '127.0.0.1'  # Endereço IP do servidor (localhost)
PORT = 9999          # Porta para operar, acima de 1024
BUFFER_SIZE = 1024   # Tamanho do payload de dados (1KB)
FILE_DIR = "files_to_send" # Diretório onde os arquivos a serem enviados estão localizados

# --- Constantes do Protocolo ---
HEADER_SIZE = 37 # 4 bytes (Seq Num) + 32 bytes (MD5) + 1 byte (EOF Flag)
PAYLOAD_SIZE = BUFFER_SIZE - HEADER_SIZE

def calculate_md5(data):
    """Calcula o checksum MD5 para um bloco de dados."""
    md5 = hashlib.md5()
    md5.update(data)
    return md5.digest()

def main():
    """Função principal para executar o servidor UDP."""
    # Garante que o diretório de arquivos exista
    if not os.path.exists(FILE_DIR):
        os.makedirs(FILE_DIR)
        print(f"Diretório '{FILE_DIR}' criado. Coloque arquivos aqui para transferência.")

    # Criação do socket UDP
    # AF_INET para IPv4, SOCK_DGRAM para UDP
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Vincula o socket ao endereço e porta especificados
    server_socket.bind((HOST, PORT))
    print(f"[*] Servidor UDP escutando em {HOST}:{PORT}")
    print(f"[*] Servindo arquivos do diretório: '{FILE_DIR}'")

    # Dicionário para armazenar segmentos de arquivos para retransmissão
    file_segments_cache = {}

    while True:
        try:
            # Aguarda por uma requisição do cliente
            request, client_address = server_socket.recvfrom(BUFFER_SIZE)
            request_str = request.decode('utf-8')
            print(f"\n[+] Recebida requisição de {client_address}: {request_str}")

            # --- Processamento da Requisição ---
            if request_str.startswith("GET /"):
                filename = request_str.split(" ")[1].strip("/")
                filepath = os.path.join(FILE_DIR, filename)

                if os.path.exists(filepath):
                    print(f"[*] Arquivo '{filename}' encontrado. Iniciando transferência.")
                    
                    # Lê o arquivo e o divide em segmentos
                    segments = []
                    with open(filepath, 'rb') as f:
                        seq_num = 0
                        while True:
                            data = f.read(PAYLOAD_SIZE)
                            if not data:
                                break # Fim do arquivo
                            
                            segments.append((seq_num, data))
                            seq_num += 1
                    
                    # Armazena os segmentos em cache para possível retransmissão
                    file_segments_cache[client_address] = segments
                    total_segments = len(segments)
                    print(f"[*] Arquivo dividido em {total_segments} segmentos.")

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
                        time.sleep(0.0001) # Pequeno delay para não sobrecarregar redes rápidas
                    
                    print(f"\n[*] Transferência de '{filename}' para {client_address} concluída.")

                else:
                    # Arquivo não encontrado, envia mensagem de erro
                    error_message = "ERROR: Arquivo nao encontrado".encode('utf-8')
                    server_socket.sendto(error_message, client_address)
                    print(f"[!] Erro: Arquivo '{filename}' não encontrado. Mensagem de erro enviada.")
            
            # --- Lógica de Retransmissão ---
            elif request_str.startswith("RETRANSMIT:"):
                missing_seq_nums_str = request_str.split(":")[1]
                missing_seq_nums = [int(n) for n in missing_seq_nums_str.split(',') if n]
                
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

        except Exception as e:
            print(f"[!] Ocorreu um erro: {e}")

if __name__ == "__main__":
    main()