import socket
import hashlib
import random
import time
import os

# --- Configurações do Cliente ---
BUFFER_SIZE = 1024
DOWNLOAD_DIR = "downloads"

# --- Constantes do Protocolo ---
# CORREÇÃO: O hash MD5 via .digest() tem 16 bytes, não 32.
HEADER_SIZE = 21 # 4 (Seq Num) + 16 (MD5) + 1 (EOF)

def calculate_md5(data):
    """Calcula o checksum MD5 para um bloco de dados."""
    md5 = hashlib.md5()
    md5.update(data)
    return md5.digest()

def parse_address(user_input):
    """Analisa a entrada do usuário no formato IP:PORTA/arquivo."""
    try:
        parts = user_input.split('/')
        address_part = parts[0]
        filename = '/'.join(parts[1:])
        
        ip, port_str = address_part.split(':')
        port = int(port_str)
        return ip, port, filename
    except (ValueError, IndexError):
        return None, None, None

def main():
    """Função principal para executar o cliente UDP."""
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"Diretório '{DOWNLOAD_DIR}' criado para salvar os arquivos.")
    
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(2.0)

    while True:
        user_input = input("\nDigite o endereço do servidor e o arquivo (ex: 127.0.0.1:9999/large_file.txt): ")
        if user_input.lower() == 'sair':
            break

        server_ip, server_port, filename = parse_address(user_input)
        if not all([server_ip, server_port, filename]):
            print("Formato inválido. Use @IP:PORTA/nome_do_arquivo.ext")
            continue
        
        server_address = (server_ip, server_port)
        
        loss_rate_str = input("Digite a taxa de perda de pacotes em % (ex: 10 para 10% de perda, 0 para sem perda): ")
        try:
            loss_rate = int(loss_rate_str) / 100.0
        except ValueError:
            print("Taxa de perda inválida. Usando 0%.")
            loss_rate = 0.0

        try:
            print(f"[*] Solicitando arquivo '{filename}' para {server_address}...")
            request = f"GET /{filename}".encode('utf-8')
            client_socket.sendto(request, server_address)

            received_segments = {}
            total_segments_expected = -1

            while True:
                try:
                    packet, _ = client_socket.recvfrom(BUFFER_SIZE)

                    if packet.startswith(b'ERROR:'):
                        print(f"[!] Erro do Servidor: {packet.decode('utf-8')}")
                        break

                    header = packet[:HEADER_SIZE]
                    data = packet[HEADER_SIZE:]

                    # CORREÇÃO: Ajuste no fatiamento do cabeçalho para 16 bytes de checksum.
                    seq_num = int.from_bytes(header[0:4], 'big')
                    received_checksum = header[4:20]   # Fatias [4] a [19] são o checksum (16 bytes)
                    eof_flag = int.from_bytes(header[20:21], 'big') # Fatia [20] é a flag (1 byte)

                    if random.random() < loss_rate:
                        print(f"[!] Pacote {seq_num} descartado intencionalmente (simulação de perda).")
                        continue

                    calculated_checksum = calculate_md5(data)
                    if received_checksum != calculated_checksum:
                        print(f"[!] Checksum inválido para o segmento {seq_num}. Pacote descartado.")
                        continue

                    if seq_num not in received_segments:
                        received_segments[seq_num] = data
                        print(f"    -> Recebido segmento {seq_num}", end='\r')

                    if eof_flag == 1:
                        total_segments_expected = seq_num + 1

                except socket.timeout:
                    print("\n[!] Timeout: Nenhum pacote recebido.")
                    break

            if not received_segments:
                if 'packet' not in locals() or not packet.startswith(b'ERROR:'):
                    print("[!] Nenhum dado válido foi recebido do servidor.")
                continue

            # Verificação e retransmissão... (lógica inalterada, mas agora deve funcionar)
            is_complete = total_segments_expected != -1 and len(received_segments) == total_segments_expected
            
            if is_complete:
                print("\n[*] Todos os segmentos recebidos corretamente!")
            else:
                print("\n[!] Detecção de segmentos faltantes ou transmissão incompleta. Solicitando retransmissão...")
                
                last_seq_num_received = max(received_segments.keys()) if received_segments else -1
                if total_segments_expected == -1:
                    total_segments_expected = last_seq_num_received + 2 # Estimativa para buscar pelo menos o próximo

                all_possible_seqs = set(range(total_segments_expected))
                received_seqs = set(received_segments.keys())
                missing_seqs = sorted(list(all_possible_seqs - received_seqs))

                if not missing_seqs:
                    print("[!] Nenhum segmento faltante identificado, mas o arquivo pode estar incompleto. Tentando salvar...")
                else:
                    print(f"[*] Segmentos faltantes: {missing_seqs}")
                    retransmit_request = f"RETRANSMIT:{','.join(map(str, missing_seqs))}".encode('utf-8')
                    client_socket.sendto(retransmit_request, server_address)

                    retries = 0
                    while missing_seqs and retries < 3:
                        try:
                            packet, _ = client_socket.recvfrom(BUFFER_SIZE)
                            header = packet[:HEADER_SIZE]
                            data = packet[HEADER_SIZE:]

                            seq_num = int.from_bytes(header[0:4], 'big')
                            if seq_num in missing_seqs:
                                received_checksum = header[4:20]
                                calculated_checksum = calculate_md5(data)
                                if received_checksum == calculated_checksum:
                                    received_segments[seq_num] = data
                                    missing_seqs.remove(seq_num)
                                    print(f"    -> Recebido segmento retransmitido {seq_num}")
                                else:
                                    print(f"[!] Checksum inválido no segmento retransmitido {seq_num}.")
                        except socket.timeout:
                            print("[!] Timeout ao esperar por pacotes retransmitidos. Tentando novamente...")
                            retries += 1
                            client_socket.sendto(retransmit_request, server_address)
                    
                    if not missing_seqs:
                        print("[*] Todos os segmentos faltantes foram recebidos!")
                    else:
                        print(f"[!] Falha ao receber os seguintes segmentos: {missing_seqs}")


            filepath = os.path.join(DOWNLOAD_DIR, os.path.basename(filename))
            print(f"[*] Montando o arquivo em '{filepath}'...")
            
            # Só salva se tiver recebido algo
            if received_segments:
                with open(filepath, 'wb') as f:
                    for i in sorted(received_segments.keys()):
                        f.write(received_segments[i])
                print(f"[*] Download de '{filename}' concluído!")
            else:
                 print(f"[!] Download de '{filename}' falhou. Nenhum dado foi salvo.")


        except ConnectionResetError:
            print("[!] Erro: A conexão foi recusada pelo servidor. Ele está rodando?")
        except Exception as e:
            print(f"[!] Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    main()