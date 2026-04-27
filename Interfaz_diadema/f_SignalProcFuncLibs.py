# f_SignalProcFuncLibs.py
# Author: Mario Valderrama
# Institution: Universidad de los Andes
# Last Update: Nov 2020

from scipy import signal, stats
import scipy.optimize as opt
import numpy as np
import statistics
import struct as st

def f_GetIIRFilter(p_FsHz, p_PassFreqHz, p_StopFreqsHz, p_Type = 'bp'):
    s_AMaxPassDb = 0.5
    s_AMinstopDb = 120
    s_NyFreqHz = p_FsHz / 2
    p_PassFreqHz = np.array(p_PassFreqHz) / s_NyFreqHz
    p_StopFreqsHz = np.array(p_StopFreqsHz) / s_NyFreqHz

    s_N, v_Wn = signal.cheb2ord(p_PassFreqHz, p_StopFreqsHz, s_AMaxPassDb, s_AMinstopDb)
    print('f_GetIIRFilter - Filter order: ', s_N)
    if p_Type == 'bs': # bandstop
        filt_FiltSOS = signal.cheby2(s_N, s_AMinstopDb, v_Wn, btype='bandstop', output='sos')
    elif p_Type == 'lp': # lowpass
        filt_FiltSOS = signal.cheby2(s_N, s_AMinstopDb, v_Wn, btype='lowpass', output='sos')
    elif p_Type == 'hp':  # lowpass
        filt_FiltSOS = signal.cheby2(s_N, s_AMinstopDb, v_Wn, btype='highpass', output='sos')
    else:
        filt_FiltSOS = signal.cheby2(s_N, s_AMinstopDb, v_Wn, btype='bandpass', output='sos')

    return filt_FiltSOS

def f_IIRBiFilter(p_FiltSOS, p_XIn):
    return signal.sosfiltfilt(p_FiltSOS, p_XIn)

def f_FFTFilter(p_XIn, p_FsHz, p_FreqPassHz):
    s_EvenLen = 0
    s_N = np.size(p_XIn)

    if np.mod(s_N, 2.0) == 0:
        p_XIn = p_XIn[0:- 1]
        s_EvenLen = 1

    s_N = np.size(p_XIn)
    s_NHalf = int((s_N - 1) / 2)
    v_Freq = np.arange(0, s_N) * p_FsHz / s_N
    v_Freq = v_Freq[0:s_NHalf + 1]

    p_FreqPassHz = np.array(p_FreqPassHz)

    v_InputSigFFT = np.fft.fft(p_XIn)
    v_InputSigFFT = v_InputSigFFT[0:s_NHalf + 1]

    v_Ind = np.zeros(s_NHalf + 1)
    v_Ind = v_Ind > 0.0
    for s_Count in range(np.size(p_FreqPassHz, 0)):
        v_Ind1 = v_Freq >= p_FreqPassHz[s_Count, 0]
        v_Ind2 = v_Freq <= p_FreqPassHz[s_Count, 1]
        v_Ind = v_Ind + (v_Ind1 & v_Ind2)

    v_InputSigFFT[~v_Ind] = (10.0 ** -10.0) * np.exp(1j * np.angle(v_InputSigFFT[~v_Ind]))
    v_InputSigFFT = np.concatenate((v_InputSigFFT,np.flip(np.conjugate(v_InputSigFFT[1:]))))
    v_FiltSig = np.real(np.fft.ifft(v_InputSigFFT))

    if s_EvenLen:
        v_FiltSig = np.concatenate((v_FiltSig, [v_FiltSig[-1]]))

    return v_FiltSig

def f_MyFFTFilter(p_XIn, p_FsHz, p_FreqPassHz):
    return f_FFTFilter(p_XIn, p_FsHz, p_FreqPassHz)

def f_GetFIRLPKaiserFilter(p_FsHz, p_CutFreqHz):
    # The Nyquist rate of the signal.
    s_NyqRate = p_FsHz / 2.0

    # The desired width of the transition from pass to stop,
    # relative to the Nyquist rate.  We'll design the filter
    # with a 5 Hz transition width.
    s_Width = 5.0 / s_NyqRate

    # The desired attenuation in the stop band, in dB.
    s_RippleDb = 80.0

    # Compute the order and Kaiser parameter for the FIR filter.
    s_N, s_Beta = signal.kaiserord(s_RippleDb, s_Width)
    print('f_GetFIRLPKaiserFilter - Filter order: ', s_N)

    # Use firwin with a Kaiser window to create a lowpass FIR filter.
    v_FilterTaps = signal.firwin(s_N, p_CutFreqHz / s_NyqRate, window=('kaiser', s_Beta))

    return v_FilterTaps

def f_GetFIRBPKaiserFilter(p_FsHz, p_CutFreqsHz, stopband=False):

    p_CutFreqsHz = np.array(p_CutFreqsHz)

    # The Nyquist rate of the signal.
    s_NyqRate = p_FsHz / 2.0

    # The desired width of the transition from pass to stop,
    # relative to the Nyquist rate.  We'll design the filter
    # with a 5 Hz transition width.
    s_WidthIni = 5.0
    s_Width = s_WidthIni / s_NyqRate

    # The desired attenuation in the stop band, in dB.
    s_RippleDb = 80.0

    # Compute the order and Kaiser parameter for the FIR filter.
    s_N, s_Beta = signal.kaiserord(s_RippleDb, s_Width)
    print('f_GetFIRBPKaiserFilter - Filter order: ', s_N)

    # Use firwin with a Kaiser window to create a lowpass FIR filter.
    if stopband:
        while np.mod(s_N, 2) == 0:
            s_WidthIni += 1.0
            s_Width = s_WidthIni / s_NyqRate
            s_N, s_Beta = signal.kaiserord(s_RippleDb, s_Width)

    v_FilterTaps = signal.firwin(s_N, p_CutFreqsHz / s_NyqRate,
                                 window=('kaiser', s_Beta), pass_zero=stopband)

    return v_FilterTaps

def f_GaborTFTransform(p_XIn, p_FsHz, p_F1Hz, p_F2Hz, p_FreqResHz, p_NumCycles,
                       p_TimeAveSec=0.0):
    # print('[f_GaborTFTransform] - TF generation...')

    # Creamos un vector de tiempo en segundos
    v_TimeArray = np.arange(0, np.size(p_XIn))
    v_TimeArray = v_TimeArray - v_TimeArray[int(np.floor(np.size(v_TimeArray) / 2))]
    v_TimeArray = v_TimeArray / p_FsHz

    # Definimos un rango de frecuencias
    # las cuales usaremos para crear nuestros
    # patrones oscilatorios de prueba
    # En este caso generaremos patrones para
    # frecuencias entre 1 y 50 Hz con pasos
    # de 0.25 Hz
    v_FreqTestHz = np.arange(p_F1Hz, p_F2Hz + p_FreqResHz, p_FreqResHz)

    # Creamos una matriz que usaremos para
    # almacenar el resultado de las
    # convoluciones sucesivas. En esta matriz,
    # cada fila corresponde al resultado de
    # una convolución y cada columna a todos
    # los desplazamientos de tiempo.
    if p_TimeAveSec > 0:
        s_TimeAveHalfSam = int(np.floor(p_TimeAveSec * p_FsHz / 2))
        s_TimeAveSam = int(s_TimeAveHalfSam * 2 + 1)
        s_FirstInd = 0
        s_SizeAve = 0
        while True:
            s_LastInd = s_FirstInd + s_TimeAveSam
            if s_LastInd >= np.size(p_XIn):
                break
            s_FirstInd += s_TimeAveSam
            s_SizeAve += 1
        m_ConvMat = np.zeros([np.size(v_FreqTestHz), s_SizeAve], dtype=complex)
    else:
        m_ConvMat = np.zeros([np.size(v_FreqTestHz), np.size(p_XIn)], dtype=complex)

    # Se obtiene la transformada de Fourier
    # de la señal p_XIn para usarla en cada iteración
    p_XInfft = np.fft.fft(p_XIn)

    # Ahora creamos un procedimiento iterativo
    # que recorra todas las frecuencias de prueba
    # definidas en el arreglo v_FreqTestHz
    for s_FreqIter in range(np.size(v_FreqTestHz)):
        # Generamos una señal sinusoidal de prueba
        # que oscile a la frecuencia de la iteración
        # s_FreqIter (v_FreqTestHz[s_FreqIter]) y que tenga
        # la misma longitud que la señal p_XIn.
        # En este caso usamos una exponencial compleja.
        xtest = np.exp(1j * 2.0 * np.pi * v_FreqTestHz[s_FreqIter] * v_TimeArray)

        # Creamos una ventana gaussina para
        # limitar nuestro patrón en el tiempo
        # Definimos la desviación estándar de
        # acuerdo al número de ciclos definidos
        # Dividimos entre 2 porque para un ventana
        # gaussiana, una desviación estándar
        # corresponde a la mitad del ancho de la ventana
        xtestwinstd = ((1.0 / v_FreqTestHz[s_FreqIter]) * p_NumCycles) / 2.0
        # Definimos nuestra ventana gaussiana
        xtestwin = np.exp(-0.5 * (v_TimeArray / xtestwinstd) ** 2.0)
        # Multiplicamos la señal patrón por
        # la ventana gaussiana
        xtest = xtest * xtestwin

        # Para cada sinusoidal de prueba obtenemos
        # el resultado de la convolución con la señal p_XIn
        # En este caso nos toca calcular la convolución
        # separadamente para la parte real e imaginaria
        # m_ConvMat[s_FreqIter, :] = np.convolve(p_XIn, np.real(xtest), 'same') + \
        #                        1j * np.convolve(p_XIn, np.imag(xtest), 'same')

        # Se obtine la transformada de Fourier del patrón
        fftxtest = np.fft.fft(xtest)
        # Se toma únicamente la parte real para evitar
        # corrimientos de fase
        fftxtest = abs(fftxtest)
        # Se obtine el resultado de la convolución realizando
        # la multiplicación de las transformadas de Fourier de
        # la señal p_XIn por la del patrón
        if p_TimeAveSec > 0:
            v_ConvArray = np.fft.ifft(p_XInfft * fftxtest)
            v_MeanConvArray = np.zeros(s_SizeAve, dtype=complex)
            s_FirstInd = 0
            s_Ind = 0
            while True:
                s_LastInd = s_FirstInd + s_TimeAveSam
                if s_LastInd >= np.size(p_XIn):
                    break
                v_MeanConvArray[s_Ind] = np.mean(np.abs(v_ConvArray[s_FirstInd:s_LastInd]))
                s_Ind += 1
                s_FirstInd += s_TimeAveSam
                m_ConvMat[s_FreqIter, :] = v_MeanConvArray
        else:
            m_ConvMat[s_FreqIter, :] = np.fft.ifft(p_XInfft * fftxtest)

    v_TimeArray = v_TimeArray - v_TimeArray[0]
    if p_TimeAveSec > 0:
        v_Ind = np.arange(0, s_SizeAve) * s_TimeAveSam
        v_Ind += s_TimeAveHalfSam
        v_TimeArray = v_TimeArray[v_Ind]

    return m_ConvMat, v_TimeArray, v_FreqTestHz

def f_WindowedGaussianFT(p_XIn, p_FsHz, p_F1Hz, p_F2Hz, p_FreqResHz,
                         p_WinSizeSec, p_TimeStepSec=0.0):

    v_TimeArraySec = np.arange(0, len(p_XIn)) / p_FsHz
    if p_TimeStepSec <= 0.0:
        v_TimeArray = v_TimeArraySec
    else:
        v_TimeArray = np.arange(0, v_TimeArraySec[-1], p_TimeStepSec)

    v_FreqArray = np.arange(0, len(v_TimeArray)) * p_FsHz / len(v_TimeArray)
    v_FreqsInd = np.where((v_FreqArray >= p_F1Hz) & (v_FreqArray <= p_F2Hz))
    v_FreqsInd = v_FreqsInd[0]
    if len(v_FreqsInd) == 0:
        print('[f_WindowedGaussianFT] - ERROR in len(p_FreqsInd) == 0')
        return

    v_FreqArray = v_FreqArray[v_FreqsInd]
    m_TFMat = np.zeros((len(v_FreqsInd), len(v_TimeArray)))
    s_StDevSec = p_WinSizeSec / 2
    s_TimeCount = 0
    for s_TimeStep in v_TimeArray:
        v_Win = np.exp(-0.5 * ((v_TimeArraySec - s_TimeStep) / s_StDevSec)**2)
        v_FFTAux = np.fft.fft(p_XIn * v_Win)
        m_TFMat[:, s_TimeCount] = v_FFTAux[v_FreqsInd]
        s_TimeCount += 1

    return m_TFMat, v_TimeArray, v_FreqArray

def f_SigRemSpectralTrend(p_Sig, p_FsHz, p_InFreqs, p_OutFreqs=[]):

    s_IsEven = 0
    if np.mod(len(p_Sig), 2) == 0:
        p_Sig = p_Sig[:-1]
        s_IsEven = 1

    v_SigFFT = np.fft.fft(p_Sig)
    v_Freqs = np.arange(0, len(v_SigFFT)) * p_FsHz / len(v_SigFFT)

    p_InFreqs = np.array(p_InFreqs)
    p_OutFreqs = np.array(p_OutFreqs)
    v_FreqsInd = np.where((v_Freqs >= p_InFreqs[0]) & (v_Freqs <= p_InFreqs[1]))
    if len(p_OutFreqs) == 0:
        v_FreqsRegInd = v_FreqsInd
    else:
        v_FreqsRegInd = np.where(((v_Freqs >= p_InFreqs[0]) & (v_Freqs <= p_OutFreqs[0])) &
                                 ((v_Freqs >= p_OutFreqs[1]) & (v_Freqs <= p_InFreqs[1])))

    v_SigFFTRegLog = np.log10(np.abs(v_SigFFT[v_FreqsRegInd]))
    v_FreqsRegLog = np.log10(v_Freqs[v_FreqsRegInd])
    v_SigFFTLog = np.log10(np.abs(v_SigFFT[v_FreqsInd]))
    v_FreqsLog = np.log10(v_Freqs[v_FreqsInd])

    v_Pol = np.polyfit(v_FreqsRegLog, v_SigFFTRegLog, 1)
    v_RegLogMag = np.polyval(v_Pol, v_FreqsLog)

    v_SigFFT[v_FreqsInd] = (10 ** (v_SigFFTLog - v_RegLogMag)) * \
                              np.exp(1j * np.angle(v_SigFFT[v_FreqsInd]))

    s_HalfLen = int((len(p_Sig) - 1) / 2)
    v_SigFFT[s_HalfLen + 1:] = np.flip(np.conjugate(v_SigFFT[1:s_HalfLen + 1]))
    v_SigWhite = np.real(np.fft.ifft(v_SigFFT))

    if s_IsEven:
        v_SigWhite = np.concatenate((v_SigWhite, [1 * v_SigWhite[-1]]))

    return v_SigWhite

def f_RemoveLinearTrend(p_Sig, p_FsHz=0):
    v_X = np.arange(0, len(p_Sig))
    if p_FsHz > 0:
        v_X /= p_FsHz

    v_Coeff = stats.siegelslopes(p_Sig, v_X)
    v_FlatSig = p_Sig - v_Coeff[1] + v_Coeff[0] * v_X

    return v_FlatSig

def f_TFNormZHo(p_InComplexMat):
    '''
    This function uses the time-frequency normalization procedure proposed by:
    Roehri N, Lina JM, Mosher JC, Bartolomei F, Benar CG.
    Time-Frequency Strategies for Increasing High-Frequency Oscillation
    Detectability in Intracerebral EEG.
    IEEE Trans Biomed Eng. 2016 Dec;63(12):2595-2606.
    :param p_InComplexMat: Time-Frequency complex matrix with frequencies
    in rows and time in columns
    :return: m_NormMat: Normalized Time-Frequency complex matrix
    '''

    def f_Gauss(x, a, x0, sigma):
        return a * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))

    m_NormMat = p_InComplexMat
    m_InComplexMatRel = np.real(p_InComplexMat)
    m_InComplexMatImg = np.imag(p_InComplexMat)

    for s_FreqCount in range(np.size(p_InComplexMat, 0)):
        v_Quantiles = statistics.quantiles(m_InComplexMatRel[s_FreqCount, :])
        s_IQR = v_Quantiles[2] - v_Quantiles[0]
        s_L1 = v_Quantiles[0] - 1.5 * s_IQR
        s_L2 = v_Quantiles[2] + 1.5 * s_IQR
        v_Vals = np.where((m_InComplexMatRel[s_FreqCount, :] >= s_L1) &
                          (m_InComplexMatRel[s_FreqCount, :] <= s_L2))
        v_Vals = v_Vals[0]

        v_Hist, v_Edges = np.histogram(v_Vals, int(len(v_Vals) * 0.20))
        s_D1 = v_Edges[1] - v_Edges[0]
        s_D1Half = s_D1 / 2
        v_Edges = np.arange(v_Edges[0] + s_D1Half, v_Edges[-1], s_D1)
        v_Params, v_PCov = opt.curve_fit(f_Gauss, v_Edges, v_Hist)

        v_ZHoRel = (m_InComplexMatRel[s_FreqCount, :] - v_Params[1]) / v_Params[2]

        v_Quantiles = statistics.quantiles(m_InComplexMatImg[s_FreqCount, :])
        s_IQR = v_Quantiles[2] - v_Quantiles[0]
        s_L1 = v_Quantiles[0] - 1.5 * s_IQR
        s_L2 = v_Quantiles[2] + 1.5 * s_IQR
        v_Vals = np.where((m_InComplexMatImg[s_FreqCount, :] >= s_L1) &
                          (m_InComplexMatImg[s_FreqCount, :] <= s_L2))
        v_Vals = v_Vals[0]

        v_Hist, v_Edges = np.histogram(v_Vals, int(len(v_Vals) * 0.20))
        s_D1 = v_Edges[1] - v_Edges[0]
        s_D1Half = s_D1 / 2
        v_Edges = np.arange(v_Edges[0] + s_D1Half, v_Edges[-1], s_D1)
        v_Params, v_PCov = opt.curve_fit(f_Gauss, v_Edges, v_Hist)

        v_ZHoImg = (m_InComplexMatImg[s_FreqCount, :] - v_Params[1]) / v_Params[2]

        m_NormMat[s_FreqCount, :] = np.array(v_ZHoRel + 1j * v_ZHoImg)

    return m_NormMat

def f_TFNormToZScore(p_InMat):
    '''
    This function normalizes the time-frequency matrix by taking the
    ZScore of each row.
    :param p_InComplexMat: Time-Frequency matrix (abs) with frequencies
    in rows and time in columns
    :return: m_NormMat: Normalized Time-Frequency complex matrix
    '''

    m_Mean = np.mean(p_InMat, 1)
    m_Std = np.std(p_InMat, 1)

    m_Mean = np.reshape(m_Mean, (len(m_Mean), 1))
    m_Mean = np.repeat(m_Mean, np.size(p_InMat, 1), axis=1)

    if np.sum(m_Std == 0) > 0:
        m_NormMat = (p_InMat - m_Mean)
    else:
        m_Std = np.reshape(m_Std, (len(m_Std), 1))
        m_Std = np.repeat(m_Std, np.size(p_InMat, 1), axis=1)
        m_NormMat = (p_InMat - m_Mean) / m_Std

    return m_NormMat


def f_PermTest2ITCByAngleArrays(pm_Dist1, pm_Dist2, alpha=0.05, permnum=1600, returndist=False):

    s_HMean = []
    s_PMean = []
    s_HMax = []
    s_PMax = []

    s_LenX = np.size(pm_Dist1, 0)
    s_LenY = np.size(pm_Dist2, 0)

    v_ArrayTemp = np.concatenate((pm_Dist1, pm_Dist2), axis=0)
    s_LenDbl = s_LenX + s_LenY

    v_Ind = np.zeros((s_LenDbl, permnum))
    v_MeanDiffDist = np.zeros((permnum, 1))
    v_MaxDiffDist = np.zeros((permnum, 1))
    for s_PermCounter in range(permnum):
        while 1:
            v_IndOrd = np.zeros((s_LenDbl, 1))
            v_IndAux = np.random.permutation(s_LenDbl)
            v_IndOrd[v_IndAux[:s_LenX], 0] = 1
            if s_PermCounter > 0:
                v_IndOrd = v_Ind[:, 0:s_PermCounter] * np.tile(v_IndOrd, (1, s_PermCounter))
                v_IndOrd = np.sum(v_IndOrd, axis=0)
                v_IndOrd = np.nonzero(v_IndOrd == s_LenX)
                v_IndOrd = v_IndOrd[0]
                if len(v_IndOrd) > 0:
                    continue

            v_IndAux = v_IndAux[:s_LenX]
            break

        v_Ind[v_IndAux, s_PermCounter] = 1

        s_MeanX = np.abs(np.mean(np.exp(1j * v_ArrayTemp[v_Ind[:, s_PermCounter] == 1, :]), axis=0))
        s_MeanY = np.abs(np.mean(np.exp(1j * v_ArrayTemp[v_Ind[:, s_PermCounter] == 0, :]), axis=0))

        v_MaxDiffDist[s_PermCounter] = np.max(s_MeanX) - np.max(s_MeanY)
        v_MeanDiffDist[s_PermCounter] = np.mean(s_MeanX) - np.mean(s_MeanY)

    v_MaxDiffDist = np.sort(np.abs(v_MaxDiffDist), axis=0)
    v_MeanDiffDist = np.sort(np.abs(v_MeanDiffDist), axis=0)

    s_MeanX = np.abs(np.mean(np.exp(1j * v_ArrayTemp[:s_LenX, :]), axis=0))
    s_MeanY = np.abs(np.mean(np.exp(1j * v_ArrayTemp[s_LenX:, :]), axis=0))
    s_MaxDiffRef = np.abs(np.max(s_MeanX) - np.max(s_MeanY))
    s_MeanDiffRef = np.abs(np.mean(s_MeanX) - np.mean(s_MeanY))

    s_HMean = 0
    s_PMean = np.where(v_MeanDiffDist >= s_MeanDiffRef)
    s_PMean = s_PMean[0]
    if len(s_PMean) == 0:
        s_PMean = 1 / (len(v_MeanDiffDist) + 1)
        s_HMean = 1
    else:
        s_PMean = (len(v_MeanDiffDist) - s_PMean[0]) / len(v_MeanDiffDist)
        if s_PMean <= alpha:
            s_HMean = 1

    s_HMax = 0
    s_PMax = np.where(v_MaxDiffDist >= s_MaxDiffRef)
    s_PMax = s_PMax[0]
    if len(s_PMax) == 0:
        s_PMax = 1 / (len(v_MaxDiffDist) + 1)
        s_HMax = 1
    else:
        s_PMax = (len(v_MaxDiffDist) - s_PMax[0]) / len(v_MaxDiffDist)
        if s_PMax <= alpha:
            s_HMax = 1

    if returndist:
        return s_HMean, s_PMean, s_HMax, s_PMax, v_MeanDiffDist, v_MaxDiffDist
    else:
        return s_HMean, s_PMean, s_HMax, s_PMax


def f_PermTest2(pv_Dist1, pv_Dist2, alpha=0.05, permnum=1600, returndist=False):

    v_H = []
    v_P = []
    v_TDist = []

    s_LenX = len(pv_Dist1)
    s_LenY = len(pv_Dist2)

    v_ArrayTemp = np.concatenate((pv_Dist1, pv_Dist2))
    s_LenDbl = s_LenX + s_LenY

    v_Ind = np.zeros((s_LenDbl, permnum))
    v_MeanDiffDist = np.zeros(permnum)
    v_MedianDiffDist = np.zeros(permnum)
    v_MeanDevDist = np.zeros(permnum)
    v_TDist = np.zeros(permnum)

    for s_PermCounter in range(permnum):
        while 1:
            v_IndOrd = np.zeros((s_LenDbl, 1))
            v_IndAux = np.random.permutation(s_LenDbl)
            v_IndOrd[v_IndAux[:s_LenX], 0] = 1
            if s_PermCounter > 0:
                v_IndOrd = v_Ind[:, 0:s_PermCounter] * np.tile(v_IndOrd, (1, s_PermCounter))
                v_IndOrd = np.sum(v_IndOrd, axis=0)
                v_IndOrd = np.nonzero(v_IndOrd == s_LenX)
                v_IndOrd = v_IndOrd[0]
                if len(v_IndOrd) > 0:
                    continue

            v_IndAux = v_IndAux[:s_LenX]
            break

        v_Ind[v_IndAux, s_PermCounter] = 1

        s_MeanX = np.mean(v_ArrayTemp[v_Ind[:, s_PermCounter] == 1])
        s_MeanY = np.mean(v_ArrayTemp[v_Ind[:, s_PermCounter] == 0])
        v_MeanDiffDist[s_PermCounter] = s_MeanX - s_MeanY

        s_MedianX = np.median(v_ArrayTemp[v_Ind[:, s_PermCounter] == 1])
        s_MedianY = np.median(v_ArrayTemp[v_Ind[:, s_PermCounter] == 0])
        v_MedianDiffDist[s_PermCounter] = s_MedianX - s_MedianY

        v_MeanDevDist[s_PermCounter] = np.mean(np.abs(v_ArrayTemp[v_Ind[:, s_PermCounter] == 1] - s_MedianX)) / \
                                       np.mean(np.abs(v_ArrayTemp[v_Ind[:, s_PermCounter] == 0] - s_MedianY))

        s_VarX = np.var(v_ArrayTemp[v_Ind[:, s_PermCounter] == 1])
        s_VarY = np.var(v_ArrayTemp[v_Ind[:, s_PermCounter] == 0])

        v_TDist[s_PermCounter] = (v_MeanDiffDist[s_PermCounter]) / \
                                 np.sqrt((s_VarX / s_LenX) + (s_VarY / s_LenY))


    v_MeanDiffDist = np.sort(abs(v_MeanDiffDist))
    v_MedianDiffDist = np.sort(abs(v_MedianDiffDist))
    v_MeanDevDist = np.sort(abs(v_MeanDevDist))
    v_TDist = np.sort(abs(v_TDist))

    s_MeanX = np.mean(v_ArrayTemp[:s_LenX])
    s_MeanY = np.mean(v_ArrayTemp[s_LenX:])
    s_MeanDiffRef = s_MeanX - s_MeanY

    s_MedianX = np.median(v_ArrayTemp[:s_LenX])
    s_MedianY = np.median(v_ArrayTemp[s_LenX:])
    s_MedianDiffRef = s_MedianX - s_MedianY

    s_MeanDevRef = np.mean(np.abs(v_ArrayTemp[:s_LenX] - s_MedianX)) / \
                   np.mean(np.abs(v_ArrayTemp[s_LenX:] - s_MedianY))

    s_VarX = np.var(v_ArrayTemp[:s_LenX])
    s_VarY = np.var(v_ArrayTemp[s_LenX:])
    s_TRef = (s_MeanX - s_MeanY) / np.sqrt((s_VarX / s_LenX) + (s_VarY / s_LenY))

    s_TotalStats = 4
    s_StatCounter = 0
    v_H = np.zeros(s_TotalStats)
    v_P = np.zeros(s_TotalStats)

    s_MeanDiffRef = np.abs(s_MeanDiffRef)
    s_MedianDiffRef = np.abs(s_MedianDiffRef)
    s_MeanDevRef = np.abs(s_MeanDevRef)
    s_TRef = np.abs(s_TRef)

    s_H = 0
    s_P = np.where(v_MeanDiffDist >= s_MeanDiffRef)
    s_P = s_P[0]
    if len(s_P) == 0:
        s_P = 1 / (len(v_MeanDiffDist) + 1)
        s_H = 1
    else:
        s_P = (len(v_MeanDiffDist) - s_P[0]) / len(v_MeanDiffDist)
        if s_P <= alpha:
            s_H = 1

    v_H[s_StatCounter] = s_H
    v_P[s_StatCounter] = s_P

    s_H = 0
    s_P = np.where(v_MedianDiffDist >= s_MedianDiffRef)
    s_P = s_P[0]
    if len(s_P) == 0:
        s_P = 1 / (len(v_MedianDiffDist) + 1)
        s_H = 1
    else:
        s_P = (len(v_MedianDiffDist) - s_P[0]) / len(v_MedianDiffDist)
        if s_P <= alpha:
            s_H = 1

    s_StatCounter = s_StatCounter + 1
    v_H[s_StatCounter] = s_H
    v_P[s_StatCounter] = s_P

    s_H = 0
    s_P = np.where(v_MeanDevDist >= s_MeanDevRef)
    s_P = s_P[0]
    if len(s_P) == 0:
        s_P = 1 / (len(v_MeanDevDist) + 1)
        s_H = 1
    else:
        s_P = (len(v_MeanDevDist) - s_P[0]) / len(v_MeanDevDist)
        if s_P <= alpha:
            s_H = 1

    s_StatCounter = s_StatCounter + 1
    v_H[s_StatCounter] = s_H
    v_P[s_StatCounter] = s_P

    s_H = 0
    s_P = np.where(v_TDist >= s_TRef)
    s_P = s_P[0]
    if len(s_P) == 0:
        s_P = 1 / (len(v_TDist) + 1)
        s_H = 1
    else:
        s_P = (len(v_TDist) - s_P[0]) / len(v_TDist)
        if s_P <= alpha:
            s_H = 1

    s_StatCounter = s_StatCounter + 1
    v_H[s_StatCounter] = s_H
    v_P[s_StatCounter] = s_P

    if returndist:
        return v_H, v_P, v_MeanDiffDist, v_MedianDiffDist, v_MeanDevDist, v_TDist
    else:
        return v_H, v_P


def f_PermTest2TestMean(pv_Dist1, pv_Dist2, alpha=0.05, permnum=1600, returndist=False):

    v_H = []
    v_P = []
    v_TDist = []

    s_LenX = len(pv_Dist1)
    s_LenY = len(pv_Dist2)

    v_ArrayTemp = np.concatenate((pv_Dist1, pv_Dist2))
    s_LenDbl = s_LenX + s_LenY

    v_Ind = np.zeros((s_LenDbl, permnum))
    v_MeanDiffDist = np.zeros(permnum)

    for s_PermCounter in range(permnum):
        while 1:
            v_IndOrd = np.zeros((s_LenDbl, 1))
            v_IndAux = np.random.permutation(s_LenDbl)
            v_IndOrd[v_IndAux[:s_LenX], 0] = 1
            if s_PermCounter > 0:
                v_IndOrd = v_Ind[:, 0:s_PermCounter] * np.tile(v_IndOrd, (1, s_PermCounter))
                v_IndOrd = np.sum(v_IndOrd, axis=0)
                v_IndOrd = np.nonzero(v_IndOrd == s_LenX)
                v_IndOrd = v_IndOrd[0]
                if len(v_IndOrd) > 0:
                    continue

            v_IndAux = v_IndAux[:s_LenX]
            break

        v_Ind[v_IndAux, s_PermCounter] = 1

        s_MeanX = np.mean(v_ArrayTemp[v_Ind[:, s_PermCounter] == 1])
        s_MeanY = np.mean(v_ArrayTemp[v_Ind[:, s_PermCounter] == 0])
        v_MeanDiffDist[s_PermCounter] = s_MeanX - s_MeanY


    v_MeanDiffDist = np.sort(abs(v_MeanDiffDist))

    s_MeanX = np.mean(v_ArrayTemp[:s_LenX])
    s_MeanY = np.mean(v_ArrayTemp[s_LenX:])
    s_MeanDiffRef = s_MeanX - s_MeanY

    s_MeanDiffRef = np.abs(s_MeanDiffRef)

    s_H = 0
    s_P = np.where(v_MeanDiffDist >= s_MeanDiffRef)
    s_P = s_P[0]
    if len(s_P) == 0:
        s_P = 1 / (len(v_MeanDiffDist) + 1)
        s_H = 1
    else:
        s_P = (len(v_MeanDiffDist) - s_P[0]) / len(v_MeanDiffDist)
        if s_P <= alpha:
            s_H = 1

    return s_H, s_P

def f_GetNaoxDataBin(p_FileName, p_DataNum=5):

    s_FilHdl = open(p_FileName, 'rb')
    v_Data = s_FilHdl.read()
    v_Data = np.double(st.unpack('f'*int(len(v_Data)/4), v_Data))
    s_FilHdl.close()

    v_IndTime = np.array(np.arange(1, len(v_Data) + 1), dtype='bool')
    v_IndTime[0:len(v_Data):(p_DataNum + 1)] = False
    v_TimeArray = v_Data[(~v_IndTime).nonzero()]
    v_Data = v_Data[v_IndTime.nonzero()]

    return v_Data, v_TimeArray
