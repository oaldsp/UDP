# client.py

import socket
import hashlib
import random
import time
import os

# --- Configurações do Cliente ---
BUFFER_SIZE = 1024
DOWNLOAD_DIR = "downloads" # Diretório para salvar os arquivos baixados

# --- Constantes do Protocolo ---
HEADER_SIZE = 37 # 4 (Seq Num) + 32 (MD5) + 1 (EOF)

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
    # Garante que o diretório de downloads exista
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
        print(f"Diretório '{DOWNLOAD_DIR}' criado para salvar os arquivos.")
    
    # Criação do socket UDP
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Define um timeout para o recebimento de pacotes (crucial para detectar fim de transmissão)
    client_socket.settimeout(2.0) # 2 segundos

    while True:
        # --- Entrada do Usuário ---
        user_input = input("\nDigite o endereço do servidor e o arquivo (ex: 127.0.0.1:9999/large_file.txt): ")
        if user_input.lower() == 'sair':
            break

        server_ip, server_port, filename = parse_address(user_input)
        if not all([server_ip, server_port, filename]):
            print("Formato inválido. Use @IP:PORTA/nome_do_arquivo.ext")
            continue
        
        server_address = (server_ip, server_port)
        
        # --- Simulação de Perda ---
        loss_rate_str = input("Digite a taxa de perda de pacotes em % (ex: 10 para 10% de perda, 0 para sem perda): ")
        try:
            loss_rate = int(loss_rate_str) / 100.0
        except ValueError:
            print("Taxa de perda inválida. Usando 0%.")
            loss_rate = 0.0

        try:
            # --- Envio da Requisição ---
            print(f"[*] Solicitando arquivo '{filename}' para {server_address}...")
            request = f"GET /{filename}".encode('utf-8')
            client_socket.sendto(request, server_address)

            # --- Recepção e Montagem do Arquivo ---
            received_segments = {}
            total_segments_expected = -1 # -1 indica que ainda não sabemos o total

            while True:
                try:
                    packet, _ = client_socket.recvfrom(BUFFER_SIZE)

                    # Verifica se é uma mensagem de erro do servidor
                    if packet.startswith(b'ERROR:'):
                        print(f"[!] Erro do Servidor: {packet.decode('utf-8')}")
                        break

                    # Extrai o cabeçalho e os dados
                    header = packet[:HEADER_SIZE]
                    data = packet[HEADER_SIZE:]

                    seq_num = int.from_bytes(header[0:4], 'big')
                    received_checksum = header[4:36]
                    eof_flag = int.from_bytes(header[36:37], 'big')

                    # Simula a perda de pacotes
                    if random.random() < loss_rate:
                        print(f"[!] Pacote {seq_num} descartado intencionalmente (simulação de perda).")
                        continue # Pula o processamento deste pacote

                    # Verifica a integridade do pacote
                    calculated_checksum = calculate_md5(data)
                    if received_checksum != calculated_checksum:
                        print(f"[!] Checksum inválido para o segmento {seq_num}. Pacote descartado.")
                        continue # Descarta pacote corrompido

                    # Armazena o segmento válido
                    if seq_num not in received_segments:
                        received_segments[seq_num] = data
                        print(f"    -> Recebido segmento {seq_num}", end='\r')

                    if eof_flag == 1:
                        total_segments_expected = seq_num + 1

                except socket.timeout:
                    # O timeout pode indicar o fim da transmissão ou perda de pacotes
                    print("\n[!] Timeout: Nenhum pacote recebido.")
                    break # Sai do loop de recebimento

            # --- Verificação e Finalização ---
            if not received_segments:
                print("[!] Nenhum dado recebido do servidor.")
                continue

            # Verifica se todos os segmentos foram recebidos
            if total_segments_expected != -1 and len(received_segments) == total_segments_expected:
                print("\n[*] Todos os segmentos recebidos corretamente!")
            else:
                # --- Lógica de Retransmissão ---
                print("\n[!] Detecção de segmentos faltantes. Solicitando retransmissão...")
                
                # Assume que o último pacote recebido com sucesso define o intervalo de busca
                last_seq_num_received = max(received_segments.keys())
                if total_segments_expected == -1:
                    total_segments_expected = last_seq_num_received + 1 # Estimativa
                
                all_possible_seqs = set(range(total_segments_expected))
                received_seqs = set(received_segments.keys())
                missing_seqs = sorted(list(all_possible_seqs - received_seqs))

                if not missing_seqs:
                    print("[!] Nenhum segmento faltante identificado, mas o arquivo pode estar incompleto. Tentando salvar...")
                else:
                    print(f"[*] Segmentos faltantes: {missing_seqs}")
                    retransmit_request = f"RETRANSMIT:{','.join(map(str, missing_seqs))}".encode('utf-8')
                    client_socket.sendto(retransmit_request, server_address)

                    # Loop para receber apenas os pacotes retransmitidos
                    while missing_seqs:
                        try:
                            packet, _ = client_socket.recvfrom(BUFFER_SIZE)
                            header = packet[:HEADER_SIZE]
                            data = packet[HEADER_SIZE:]

                            seq_num = int.from_bytes(header[0:4], 'big')
                            if seq_num in missing_seqs:
                                received_checksum = header[4:36]
                                calculated_checksum = calculate_md5(data)
                                if received_checksum == calculated_checksum:
                                    received_segments[seq_num] = data
                                    missing_seqs.remove(seq_num)
                                    print(f"    -> Recebido segmento retransmitido {seq_num}")
                                else:
                                    print(f"[!] Checksum inválido no segmento retransmitido {seq_num}.")
                        except socket.timeout:
                            print("[!] Timeout ao esperar por pacotes retransmitidos. A transferência falhou.")
                            break
                    
                    if not missing_seqs:
                        print("[*] Todos os segmentos faltantes foram recebidos!")

            # --- Montagem do Arquivo ---
            filepath = os.path.join(DOWNLOAD_DIR, os.path.basename(filename))
            print(f"[*] Montando o arquivo em '{filepath}'...")
            
            with open(filepath, 'wb') as f:
                # Ordena os segmentos pela chave (número de sequência)
                for i in sorted(received_segments.keys()):
                    f.write(received_segments[i])
            
            print(f"[*] Download de '{filename}' concluído com sucesso!")

        except ConnectionResetError:
            print("[!] Erro: A conexão foi recusada pelo servidor. Ele está rodando?")
        except Exception as e:
            print(f"[!] Ocorreu um erro inesperado: {e}")

if __name__ == "__main__":
    main()