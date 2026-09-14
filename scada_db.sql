-- phpMyAdmin SQL Dump
-- version 5.2.1
-- https://www.phpmyadmin.net/
--
-- Servidor: 127.0.0.1
-- Tiempo de generación: 15-04-2026 a las 01:27:12
-- Versión del servidor: 10.4.32-MariaDB
-- Versión de PHP: 8.2.12

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Base de datos: `scada_db`
--

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `alarmas`
--

CREATE TABLE `alarmas` (
  `id` int(11) NOT NULL,
  `condicion` varchar(100) DEFAULT NULL,
  `codigo` varchar(20) DEFAULT NULL,
  `descripcion` text DEFAULT NULL,
  `estado` enum('Activa','Resuelta') NOT NULL,
  `categoria` varchar(50) DEFAULT NULL,
  `valor` decimal(10,2) DEFAULT NULL,
  `hora_inicio` datetime NOT NULL,
  `hora_fin` datetime DEFAULT NULL,
  `usuario_id` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `angulos_optimos`
--

CREATE TABLE `angulos_optimos` (
  `mes` tinyint(4) NOT NULL,
  `angulo_horizontal_optimo` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Volcado de datos para la tabla `angulos_optimos`
--

INSERT INTO `angulos_optimos` (`mes`, `angulo_horizontal_optimo`) VALUES
(1, 1),
(2, 11),
(3, 26),
(4, 40),
(5, 48),
(6, 55),
(7, 53),
(8, 46),
(9, 34),
(10, 17),
(11, 4),
(12, 0);

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `config_alarmas`
--

CREATE TABLE `config_alarmas` (
  `id` int(11) NOT NULL,
  `condicion` varchar(50) NOT NULL,
  `codigo` varchar(10) NOT NULL,
  `descripcion` varchar(100) DEFAULT NULL,
  `categoria` varchar(30) DEFAULT NULL,
  `operador` enum('>','<','>=','<=') NOT NULL,
  `umbral` float NOT NULL,
  `habilitada` tinyint(1) DEFAULT 1,
  `usuario_id` int(11) DEFAULT NULL,
  `fecha_modificacion` datetime DEFAULT current_timestamp(),
  `variable` varchar(50) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Volcado de datos para la tabla `config_alarmas`
--

INSERT INTO `config_alarmas` (`id`, `condicion`, `codigo`, `descripcion`, `categoria`, `operador`, `umbral`, `habilitada`, `usuario_id`, `fecha_modificacion`, `variable`) VALUES
(1, 'Tensión alta', 'V-001', 'Sobretensión en entrada', 'Voltaje', '>=', 78, 0, 1, '2026-03-02 14:51:53', 'voltaje_in'),
(2, 'Tensión baja', 'V-002', 'Subtensión en entrada', 'Voltaje', '<', 2, 1, 1, '2026-03-02 15:51:07', 'voltaje_in'),
(4, 'Potencia baja', 'P-001', 'Baja potencia de salida', 'Potencia', '<', 120, 0, 1, '2026-03-02 14:51:36', 'potencia_out'),
(13, 'Potencia Baja', 'P-003', 'Baja potencia de salida', 'Potencia', '<', 80, 0, 1, '2026-03-02 14:51:57', 'potencia_out'),
(14, 'Corriente Baja', 'I-001', 'Baja corriente de entrada', 'Corriente', '<', 2, 0, 1, '2026-03-02 14:51:29', 'corriente_in'),
(16, 'Corriente baja', 'I-003', 'Baja corriente de salida', 'Corriente', '<', 0.5, 1, 1, '2026-03-02 16:28:08', NULL),
(17, 'Potencia Baja', 'P-004', 'Potencia de salida baja', 'Potencia', '<', 0.5, 0, 1, '2026-03-04 16:38:38', NULL);

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `mediciones`
--

CREATE TABLE `mediciones` (
  `id` int(11) NOT NULL,
  `fecha_hora` datetime NOT NULL DEFAULT current_timestamp(),
  `corriente_in` decimal(6,2) DEFAULT NULL,
  `corriente_out` decimal(6,2) DEFAULT NULL,
  `voltaje_in` decimal(6,2) DEFAULT NULL,
  `voltaje_out` decimal(6,2) DEFAULT NULL,
  `potencia_in` decimal(8,2) DEFAULT NULL,
  `potencia_out` decimal(8,2) DEFAULT NULL,
  `angulo` int(11) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `modo_operacion`
--

CREATE TABLE `modo_operacion` (
  `id` int(11) NOT NULL,
  `fecha_hora` datetime NOT NULL,
  `modo` enum('Manual','Automatico') NOT NULL,
  `angulo_deseado` int(11) DEFAULT NULL,
  `usuario_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `registro_usuarios`
--

CREATE TABLE `registro_usuarios` (
  `id` int(11) NOT NULL,
  `usuario_id` int(11) NOT NULL,
  `hora_inicio` datetime NOT NULL,
  `hora_salida` datetime DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------

--
-- Estructura de tabla para la tabla `usuarios`
--

CREATE TABLE `usuarios` (
  `id` int(11) NOT NULL,
  `usuario` varchar(50) NOT NULL,
  `password_hash` varchar(64) NOT NULL,
  `jerarquia` enum('administrador','operador','solo_lectura') NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

--
-- Volcado de datos para la tabla `usuarios`
--

INSERT INTO `usuarios` (`id`, `usuario`, `password_hash`, `jerarquia`) VALUES
(1, 'admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9', 'administrador'),
(7, 'visor3', 'a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3', 'solo_lectura'),
(9, 'visor', '8395107bccee912451ce2415d4617f4e7fe36fa77f802f8d4050f5e726fab8a7', 'solo_lectura'),
(10, 'operador', '1725165c9a0b3698a3d01016e0d8205155820b8d7f21835ca64c0f81c728d880', 'operador');

--
-- Índices para tablas volcadas
--

--
-- Indices de la tabla `alarmas`
--
ALTER TABLE `alarmas`
  ADD PRIMARY KEY (`id`),
  ADD KEY `usuario_id` (`usuario_id`);

--
-- Indices de la tabla `angulos_optimos`
--
ALTER TABLE `angulos_optimos`
  ADD PRIMARY KEY (`mes`);

--
-- Indices de la tabla `config_alarmas`
--
ALTER TABLE `config_alarmas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `codigo` (`codigo`);

--
-- Indices de la tabla `mediciones`
--
ALTER TABLE `mediciones`
  ADD PRIMARY KEY (`id`);

--
-- Indices de la tabla `modo_operacion`
--
ALTER TABLE `modo_operacion`
  ADD PRIMARY KEY (`id`),
  ADD KEY `usuario_id` (`usuario_id`);

--
-- Indices de la tabla `registro_usuarios`
--
ALTER TABLE `registro_usuarios`
  ADD PRIMARY KEY (`id`),
  ADD KEY `usuario_id` (`usuario_id`);

--
-- Indices de la tabla `usuarios`
--
ALTER TABLE `usuarios`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `usuario` (`usuario`);

--
-- AUTO_INCREMENT de las tablas volcadas
--

--
-- AUTO_INCREMENT de la tabla `alarmas`
--
ALTER TABLE `alarmas`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `config_alarmas`
--
ALTER TABLE `config_alarmas`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=18;

--
-- AUTO_INCREMENT de la tabla `mediciones`
--
ALTER TABLE `mediciones`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `modo_operacion`
--
ALTER TABLE `modo_operacion`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `registro_usuarios`
--
ALTER TABLE `registro_usuarios`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT de la tabla `usuarios`
--
ALTER TABLE `usuarios`
  MODIFY `id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=20;

--
-- Restricciones para tablas volcadas
--

--
-- Filtros para la tabla `alarmas`
--
ALTER TABLE `alarmas`
  ADD CONSTRAINT `alarmas_ibfk_1` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Filtros para la tabla `modo_operacion`
--
ALTER TABLE `modo_operacion`
  ADD CONSTRAINT `modo_operacion_ibfk_1` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);

--
-- Filtros para la tabla `registro_usuarios`
--
ALTER TABLE `registro_usuarios`
  ADD CONSTRAINT `registro_usuarios_ibfk_1` FOREIGN KEY (`usuario_id`) REFERENCES `usuarios` (`id`);
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
