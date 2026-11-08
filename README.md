# TankSense
Proyecto grupal de Internet of Things por Ryan X. Velez Negron y Axel Algarin Diaz.

## Problema e Impacto Esperado
El problema actual es la falta de información exacta sobre la cantidad de agua que queda dentro de un tanque. Los beneficiarios de este proyecto serían las personas que utilizan tanques de almacenamiento de agua en sus hogares o negocios. La razón por la cual se escogió fue para poder conocer el nivel del agua sin tener que abrir o revisar el tanque manualmente. El resultado que se pudiera ver sería una mejor administración del agua y menos posibilidades de quedarse sin suministro.

## Diseño y Arquitectura IoT
Un sensor ultrasónico mide la distancia entre él y la superficie del agua para poder determinar el nivel que queda dentro del tanque. La información que recibe el sensor se transmite al Raspberry Pi 4, que procesa los datos y puede enviarlos a una página/app por medio de una red.

Componentes utilizados:
- (1) Sensor ultrasónico para medir la distancia al agua
- (1) Raspberry Pi 4 (leer y procesar los datos)
- (1) Plataforma web/app para presentar el nivel del tanque al usuario

Flujo de datos: Sensor ultrasónico → Raspberry Pi 4 → Cálculo del nivel de agua → Página web → Usuario

## Construcción y Funcionamiento del Prototipo
La plataforma física que se utilizará para el prototipo es una Raspberry Pi 4, conectada a un sensor ultrasónico colocado en la parte superior del tanque. El sensor medirá la distancia hasta la superficie del agua y el programa calculará el nivel aproximado.

Conexiones: Trigger → GPIO 23, Echo → GPIO 24.

Para ponerlo en funcionamiento: ajustar `ALTURA_TANQUE_CM` en el código y ejecutar `python3 tanksense.py`.

## Aportación Creativa del Grupo
Si tuviéramos tiempo adicional, le podríamos haber añadido más funciones al equipo, tales como: una notificación que indique cuando el tanque está casi vacío y un LED que muestre el nivel del agua directamente en el tanque.

## Pruebas y Resultados
- **Situación 1 (El tanque está lleno):** el sensor detecta la superficie del agua a una distancia corta. Resultado esperado: "Nivel Lleno". Resultado obtenido: actualización a "Nivel Lleno".
- **Situación 2 (El tanque está casi vacío):** el sensor detecta la superficie del agua a una distancia larga. Resultado esperado: "Nivel Muy Bajo". Resultado obtenido: actualización a "Nivel Muy Bajo".

## Costo y Viabilidad
Raspberry Pi 4: $35.00, Sensor ultrasónico: $17.00, Cables y conectores: $2.00. Costo total: $54.00.

Este proyecto tiene una gran viabilidad financiera para cualquier tipo de presupuesto, desde hogares y pequeños negocios hasta empresas privadas.

## Seguridad, Privacidad y Limitaciones
- **Vulnerabilidades:** posible pérdida de datos debido a fallas en el sensor causadas por la acumulación de suciedad dentro del tanque.
- **Privacidad y seguridad:** se implementará una red local privada y se provee seguridad a la plataforma web para asegurar el acceso a los datos.
- **Limitaciones:** la limitación principal del prototipo actual es que está diseñado para monitorear un solo tanque a la vez.

## Referencias y Créditos
- Video: Water Tank Level Control System using Raspberry Pi 4 (YouTube): https://www.youtube.com/watch?v=7Sy0g6kwcRU. Referencia de cómo medir el nivel de agua de un tanque con un Raspberry Pi 4 y un sensor ultrasónico HC-SR04.

## Presentación
El archivo de la presentación se encuentra en este repositorio: [TankSense.pptx](TankSense.pptx)
