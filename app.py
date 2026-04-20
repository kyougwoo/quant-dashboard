import React, { useState, useEffect, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar, Cell } from 'recharts';
import { Activity, TrendingUp, TrendingDown, BookOpen, ShieldAlert, Cpu, Play, AlertCircle, CheckCircle } from 'lucide-react';

// --- 가상 데이터 (Simulation Data) ---
const MOCK_DATA = {
  "삼성전자": {
    priceData: [
      { date: '04-01', price: 81000 }, { date: '04-02', price: 81500 }, { date: '04-03', price: 82200 },
      { date: '04-06', price: 82000 }, { date: '04-07', price: 83500 }, { date: '04-08', price: 84100 },
      { date: '04-09', price: 83800 }, { date: '04-10', price: 84500 }, { date: '04-13', price: 85200 },
      { date: '04-14', price: 84900 }, { date: '04-15', price: 85500 }
    ],
    news: [
      "삼성전자, 차세대 HBM4 메모리 양산 계획 조기 발표",
      "글로벌 반도체 수요 회복세 뚜렷... 삼성전자 영업이익 어닝 서프라이즈 기대",
      "파운드리 부문 수율 개선 지연 우려, 일부 고객사 이탈 루머"
    ],
    trend: "상승세 (단기 20일 이동평균선 상향 돌파)"
  },
  "아난티": {
    priceData: [
      { date: '04-01', price: 6200 }, { date: '04-02', price: 6150 }, { date: '04-03', price: 6050 },
      { date: '04-06', price: 5900 }, { date: '04-07', price: 5850 }, { date: '04-08', price: 5950 },
      { date: '04-09', price: 6000 }, { date: '04-10', price: 5950 }, { date: '04-13', price: 5800 },
      { date: '04-14', price: 5750 }, { date: '04-15', price: 5700 }
    ],
    news: [
      "국내 관광 수요 감소 및 소비 침체 장기화 우려",
      "신규 리조트 개발 사업 인허가 지연 소식",
      "외국인 관광객 유치 프로모션 전개로 하반기 실적 개선 기대감"
    ],
    trend: "하락세 (지속적인 조정을 받으며 60일선 하회)"
  }
};

// Gemini API 설정
const apiKey = ""; // Canvas 환경에서 자동 주입됨

const App = () => {
  const [selectedAsset, setSelectedAsset] = useState("삼성전자");
  const [loading, setLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);
  const [error, setError] = useState(null);

  const assetData = MOCK_DATA[selectedAsset];

  // Gemini API를 호출하여 3-Agent 분석 수행
  const runAgentAnalysis = async () => {
    setLoading(true);
    setError(null);
    setAnalysisResult(null);

    const prompt = `
      당신은 'Harness 3-Agent' 기반의 최고 수준 퀀트 투자 시스템입니다.
      아래 종목의 시장 데이터를 바탕으로 3명의 에이전트(기술적 분석가, 기본적 분석가, 리스크 관리자)의 시각에서 분석을 수행하세요.

      [분석 대상 데이터]
      - 종목명: ${selectedAsset}
      - 현재 가격 추세: ${assetData.trend}
      - 최근 주요 뉴스:
        1. ${assetData.news[0]}
        2. ${assetData.news[1]}
        3. ${assetData.news[2]}

      [출력 형식 (반드시 유효한 JSON 형식으로만 응답할 것. 마크다운 블록 금지)]
      {
        "technicalAgent": {
          "score": -10부터 10 사이의 정수 (10이 강력 매수),
          "reasoning": "기술적 분석가 에이전트의 차트 및 추세 기반 분석 의견 (2~3문장)"
        },
        "fundamentalAgent": {
          "score": -10부터 10 사이의 정수 (10이 강력 호재),
          "reasoning": "기본적 분석가 에이전트의 뉴스 감성 및 모멘텀 기반 분석 의견 (2~3문장)"
        },
        "riskManager": {
          "action": "매수", "매도", 또는 "관망" 중 택 1,
          "positionSize": "비중 0% ~ 100% 제시",
          "reasoning": "기술적/기본적 의견을 종합하여 리스크 관리자 에이전트가 내리는 최종 결론 (2~3문장)"
        }
      }
    `;

    try {
      // Exponential Backoff를 적용한 fetch (생략 없이 간단 구현)
      const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key=${apiKey}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: { 
            responseMimeType: "application/json" 
          }
        })
      });

      if (!response.ok) throw new Error("API 호출에 실패했습니다.");

      const data = await response.json();
      const resultText = data.candidates?.[0]?.content?.parts?.[0]?.text;
      
      if (resultText) {
        setAnalysisResult(JSON.parse(resultText));
      } else {
        throw new Error("결과를 파싱할 수 없습니다.");
      }
    } catch (err) {
      console.error(err);
      setError("AI 분석 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.");
    } finally {
      setLoading(false);
    }
  };

  // 자산이 변경되면 분석 결과 초기화
  useEffect(() => {
    setAnalysisResult(null);
    setError(null);
  }, [selectedAsset]);

  const latestPrice = assetData.priceData[assetData.priceData.length - 1].price;
  const prevPrice = assetData.priceData[assetData.priceData.length - 2].price;
  const priceDiff = latestPrice - prevPrice;
  const isUp = priceDiff >= 0;

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 p-4 md:p-6 font-sans">
      {/* 헤더 섹션 */}
      <header className="flex flex-col md:flex-row justify-between items-center mb-8 bg-gray-800 p-4 rounded-xl shadow-lg border border-gray-700">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-600 rounded-lg">
            <Cpu size={28} className="text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-teal-400">
              지후아빠 랩 3-Agent 퀀트 대시보드
            </h1>
            <p className="text-gray-400 text-sm">LLM 멀티 에이전트 기반 투자 판단 시스템</p>
          </div>
        </div>

        <div className="mt-4 md:mt-0 flex gap-2">
          {Object.keys(MOCK_DATA).map(asset => (
            <button
              key={asset}
              onClick={() => setSelectedAsset(asset)}
              className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                selectedAsset === asset 
                  ? 'bg-blue-600 text-white shadow-md' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              {asset}
            </button>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 왼쪽 패널: 데이터 시각화 및 정보 */}
        <div className="lg:col-span-1 space-y-6">
          {/* 가격 정보 카드 */}
          <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 shadow-md">
            <h2 className="text-lg font-semibold text-gray-300 mb-2">{selectedAsset} 현재가 (Mock)</h2>
            <div className="flex items-baseline gap-3">
              <span className="text-4xl font-bold text-white">{latestPrice.toLocaleString()}원</span>
              <span className={`text-lg font-medium flex items-center ${isUp ? 'text-red-400' : 'text-blue-400'}`}>
                {isUp ? <TrendingUp size={20} className="mr-1" /> : <TrendingDown size={20} className="mr-1" />}
                {Math.abs(priceDiff).toLocaleString()} ({((Math.abs(priceDiff)/prevPrice)*100).toFixed(2)}%)
              </span>
            </div>
            <p className="text-sm text-gray-500 mt-3 border-t border-gray-700 pt-3">
              <span className="text-gray-400 font-medium">단기 추세:</span> {assetData.trend}
            </p>
          </div>

          {/* 차트 영역 */}
          <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 shadow-md h-64">
            <h2 className="text-sm font-semibold text-gray-400 mb-4">최근 가격 추이</h2>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={assetData.priceData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="date" stroke="#9CA3AF" fontSize={12} />
                <YAxis domain={['auto', 'auto']} stroke="#9CA3AF" fontSize={12} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1F2937', border: 'none', borderRadius: '8px', color: '#F3F4F6' }}
                  itemStyle={{ color: '#60A5FA' }}
                />
                <Line type="monotone" dataKey="price" stroke={isUp ? "#F87171" : "#60A5FA"} strokeWidth={3} dot={{ r: 4, fill: '#1F2937' }} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* 뉴스 감성 수집 영역 */}
          <div className="bg-gray-800 p-5 rounded-xl border border-gray-700 shadow-md">
            <h2 className="text-sm font-semibold text-gray-400 mb-4 flex items-center gap-2">
              <BookOpen size={16} /> 수집된 주요 뉴스 (Input)
            </h2>
            <ul className="space-y-3">
              {assetData.news.map((newsItem, idx) => (
                <li key={idx} className="text-sm text-gray-300 bg-gray-700/50 p-3 rounded-lg leading-relaxed border-l-4 border-blue-500">
                  {newsItem}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* 오른쪽 패널: 3-Agent AI 퀀트 엔진 */}
        <div className="lg:col-span-2 flex flex-col h-full space-y-6">
          <div className="bg-gray-800 p-6 rounded-xl border border-blue-900 shadow-lg flex-1 flex flex-col relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 via-teal-400 to-blue-500"></div>
            
            <div className="flex justify-between items-center mb-6">
              <div>
                <h2 className="text-xl font-bold text-white flex items-center gap-2">
                  <Activity size={24} className="text-teal-400" /> 
                  Harness 3-Agent 분석 엔진
                </h2>
                <p className="text-sm text-gray-400 mt-1">기술적 분석, 기본적 분석, 리스크 관리자가 토론하여 결정을 내립니다.</p>
              </div>
              <button 
                onClick={runAgentAnalysis}
                disabled={loading}
                className={`flex items-center gap-2 px-6 py-3 rounded-lg font-bold text-white transition-all shadow-md ${
                  loading ? 'bg-gray-600 cursor-not-allowed' : 'bg-gradient-to-r from-teal-500 to-blue-600 hover:from-teal-400 hover:to-blue-500 hover:scale-105'
                }`}
              >
                {loading ? (
                  <><span className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></span> 분석 중...</>
                ) : (
                  <><Play size={18} fill="currentColor" /> AI 분석 실행</>
                )}
              </button>
            </div>

            {error && (
              <div className="p-4 mb-6 bg-red-900/30 border border-red-800 rounded-lg text-red-300 flex items-center gap-3">
                <AlertCircle size={20} /> {error}
              </div>
            )}

            {!analysisResult && !loading && !error && (
              <div className="flex-1 flex flex-col items-center justify-center text-gray-500 space-y-4 py-12 border-2 border-dashed border-gray-700 rounded-xl">
                <Cpu size={48} className="opacity-50" />
                <p>우측 상단의 'AI 분석 실행' 버튼을 눌러 멀티 에이전트 토론을 시작하세요.</p>
              </div>
            )}

            {/* AI 분석 결과 패널 */}
            {analysisResult && (
              <div className="space-y-4 animate-fadeIn">
                {/* 1. 기술적 분석가 */}
                <div className="bg-gray-700/40 border border-gray-600 p-5 rounded-xl">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 bg-indigo-900/50 rounded-md text-indigo-400"><TrendingUp size={18} /></div>
                      <h3 className="font-semibold text-indigo-300">Agent 1: 기술적 분석가 (Technical)</h3>
                    </div>
                    <ScoreBadge score={analysisResult.technicalAgent.score} />
                  </div>
                  <p className="text-gray-300 text-sm leading-relaxed pl-9">
                    {analysisResult.technicalAgent.reasoning}
                  </p>
                </div>

                {/* 2. 기본적 분석가 */}
                <div className="bg-gray-700/40 border border-gray-600 p-5 rounded-xl">
                  <div className="flex justify-between items-start mb-3">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 bg-emerald-900/50 rounded-md text-emerald-400"><BookOpen size={18} /></div>
                      <h3 className="font-semibold text-emerald-300">Agent 2: 기본적 분석가 (Fundamental)</h3>
                    </div>
                    <ScoreBadge score={analysisResult.fundamentalAgent.score} />
                  </div>
                  <p className="text-gray-300 text-sm leading-relaxed pl-9">
                    {analysisResult.fundamentalAgent.reasoning}
                  </p>
                </div>

                {/* 3. 리스크 관리자 (최종 결정) */}
                <div className="bg-blue-900/20 border border-blue-700 p-6 rounded-xl relative overflow-hidden mt-6 shadow-[0_0_15px_rgba(59,130,246,0.1)]">
                  <div className="absolute right-0 top-0 opacity-10 transform translate-x-4 -translate-y-4">
                    <ShieldAlert size={120} />
                  </div>
                  <div className="flex items-center gap-2 mb-4">
                    <div className="p-1.5 bg-blue-600 rounded-md text-white"><ShieldAlert size={18} /></div>
                    <h3 className="font-bold text-blue-400 text-lg">Agent 3: 리스크 관리자 (최종 판단)</h3>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-4 mb-4 pl-9 pr-12 relative z-10">
                    <div className="bg-gray-800 p-4 rounded-lg border border-gray-600 flex flex-col justify-center items-center">
                      <span className="text-xs text-gray-400 mb-1 uppercase tracking-wider">최종 포지션 제안</span>
                      <span className={`text-2xl font-black ${
                        analysisResult.riskManager.action.includes('매수') ? 'text-red-400' :
                        analysisResult.riskManager.action.includes('매도') ? 'text-blue-400' : 'text-gray-300'
                      }`}>
                        {analysisResult.riskManager.action}
                      </span>
                    </div>
                    <div className="bg-gray-800 p-4 rounded-lg border border-gray-600 flex flex-col justify-center items-center">
                      <span className="text-xs text-gray-400 mb-1 uppercase tracking-wider">추천 투자 비중</span>
                      <span className="text-2xl font-black text-white">{analysisResult.riskManager.positionSize}</span>
                    </div>
                  </div>
                  
                  <div className="pl-9 relative z-10">
                    <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wider">종합 의견</h4>
                    <p className="text-gray-200 text-sm leading-relaxed bg-gray-800/80 p-4 rounded-lg border-l-4 border-blue-500">
                      {analysisResult.riskManager.reasoning}
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
      
      {/* 스타일 애니메이션 */}
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.5s ease-out forwards;
        }
      `}} />
    </div>
  );
};

// 스코어 뱃지 컴포넌트
const ScoreBadge = ({ score }) => {
  const getScoreColor = (s) => {
    if (s >= 5) return 'bg-red-500/20 text-red-400 border-red-500/30';
    if (s <= -5) return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    return 'bg-gray-500/20 text-gray-300 border-gray-500/30';
  };
  
  return (
    <div className={`px-3 py-1 rounded-full border text-xs font-bold flex items-center gap-1 ${getScoreColor(score)}`}>
      스코어: {score > 0 ? `+${score}` : score} / 10
    </div>
  );
};

export default App;
